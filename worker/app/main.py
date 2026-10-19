import json
import logging
import signal
import time

from sqlalchemy import select

from app.config import get_settings
from app.database import session_factory
from app.integrations.queue import SQSQueue, publish_outbox
from app.models import Followup, SearchJob, utcnow
from app.services.business import trigger_followup
from app.workflow.discovery import process_job

running = True
logger = logging.getLogger("qima.worker")


def stop(*_):
    global running
    running = False


def tick(queue=None):
    settings = get_settings()
    publish_outbox(queue)
    if settings.queue_provider == "local":
        with session_factory()() as db:
            jobs = list(
                db.scalars(
                    select(SearchJob)
                    .where(SearchJob.status.in_(["QUEUED", "RUNNING", "FAILED_RETRYABLE"]))
                    .order_by(SearchJob.created_at)
                    .limit(10)
                )
            )
            ids = [job.id for job in jobs]
        for job_id in ids:
            process_job(job_id, f"local:{job_id}")
        with session_factory()() as db:
            for followup in db.scalars(
                select(Followup).where(Followup.status == "SCHEDULED", Followup.due_at <= utcnow())
            ):
                trigger_followup(db, followup.id)
            db.commit()
    else:
        queue = queue or SQSQueue()
        for message in queue.receive():
            try:
                data = json.loads(message["Body"])
                if data.get("schema_version") != 1 or bool(data.get("job_id")) == bool(
                    data.get("followup_id")
                ):
                    raise ValueError("Invalid queue message")
                with queue.heartbeat(message["ReceiptHandle"]):
                    if data.get("followup_id"):
                        with session_factory()() as db:
                            complete = trigger_followup(db, data["followup_id"])
                            db.commit()
                    else:
                        complete = process_job(data["job_id"], message["MessageId"])
                if complete:
                    queue.ack(message["ReceiptHandle"])
            except Exception as exc:
                logger.warning(
                    json.dumps(
                        {
                            "event": "queue.processing_failed",
                            "error_type": type(exc).__name__,
                            "message_id": message.get("MessageId"),
                        }
                    )
                )


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    logger.info(json.dumps({"event": "worker.started", "provider": get_settings().queue_provider}))
    while running:
        try:
            tick()
        except Exception as exc:
            logger.error(json.dumps({"event": "worker.tick_failed", "error_type": type(exc).__name__}))
        time.sleep(2)


if __name__ == "__main__":
    main()
