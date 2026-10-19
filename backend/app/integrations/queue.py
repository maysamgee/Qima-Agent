import json
import threading
from contextlib import contextmanager

from sqlalchemy import select

from app.config import get_settings
from app.database import session_factory
from app.integrations.aws import aws_client
from app.models import Followup, OutboxEvent, utcnow


class SQSQueue:
    def __init__(self, client=None):
        self.client = client or aws_client("sqs")
        self.settings = get_settings()

    def publish(self, payload):
        return self.client.send_message(
            QueueUrl=self.settings.discovery_queue_url, MessageBody=json.dumps(payload)
        )["MessageId"]

    def receive(self):
        return self.client.receive_message(
            QueueUrl=self.settings.discovery_queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=20,
            VisibilityTimeout=self.settings.queue_visibility_seconds,
            MessageSystemAttributeNames=["ApproximateReceiveCount"],
        ).get("Messages", [])

    def ack(self, receipt):
        self.client.delete_message(QueueUrl=self.settings.discovery_queue_url, ReceiptHandle=receipt)

    @contextmanager
    def heartbeat(self, receipt):
        stop = threading.Event()
        errors = []

        def extend():
            while not stop.wait(max(1, self.settings.queue_visibility_seconds // 3)):
                try:
                    self.client.change_message_visibility(
                        QueueUrl=self.settings.discovery_queue_url,
                        ReceiptHandle=receipt,
                        VisibilityTimeout=self.settings.queue_visibility_seconds,
                    )
                except Exception as exc:
                    errors.append(type(exc).__name__)

        thread = threading.Thread(target=extend, daemon=True)
        thread.start()
        try:
            yield errors
        finally:
            stop.set()
            thread.join(timeout=1)


def schedule_followup(followup, client=None):
    settings = get_settings()
    if not settings.scheduler_role_arn:
        raise ValueError("SCHEDULER_ROLE_ARN is required in SQS mode")
    queue = aws_client("sqs")
    queue_arn = queue.get_queue_attributes(
        QueueUrl=settings.discovery_queue_url, AttributeNames=["QueueArn"]
    )["Attributes"]["QueueArn"]
    scheduler = client or aws_client("scheduler")
    kwargs = dict(
        Name=f"qima-followup-{followup.id}",
        GroupName=settings.scheduler_group,
        ScheduleExpression=f"at({followup.due_at.strftime('%Y-%m-%dT%H:%M:%S')})",
        ScheduleExpressionTimezone="UTC",
        FlexibleTimeWindow={"Mode": "OFF"},
        ActionAfterCompletion="DELETE",
        Target={
            "Arn": queue_arn,
            "RoleArn": settings.scheduler_role_arn,
            "Input": json.dumps({"followup_id": followup.id, "schema_version": 1}),
            "RetryPolicy": {"MaximumEventAgeInSeconds": 3600, "MaximumRetryAttempts": 3},
        },
        ClientToken=followup.id,
    )
    try:
        scheduler.create_schedule(**kwargs)
    except scheduler.exceptions.ConflictException:
        # Stable name means the same durable follow-up already has a schedule.
        pass


def publish_outbox(queue=None):
    settings = get_settings()
    with session_factory()() as db:
        events = list(
            db.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.published_at.is_(None))
                .order_by(OutboxEvent.created_at)
                .limit(20)
                .with_for_update(skip_locked=True)
            )
        )
        for event in events:
            event.attempts += 1
            try:
                if settings.queue_provider == "sqs":
                    if event.event_type == "FOLLOWUP_SCHEDULE":
                        followup = db.get(Followup, event.payload["followup_id"])
                        if followup and followup.status == "SCHEDULED":
                            schedule_followup(followup)
                    else:
                        (queue or SQSQueue()).publish(event.payload)
                event.published_at = utcnow()
                event.last_error = None
            except Exception as exc:
                event.last_error = type(exc).__name__ + ": publication deferred for retry"
        db.commit()
        return len(events)
