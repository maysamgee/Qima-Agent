import io
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import boto3
import jwt
import pytest
from botocore.response import StreamingBody
from botocore.stub import ANY, Stubber
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.auth import current_actor
from app.config import get_settings
from app.integrations.queue import SQSQueue, schedule_followup
from app.integrations.storage import S3StorageProvider


def aws_test_client(service):
    return boto3.client(
        service, region_name="us-east-1", aws_access_key_id="testing", aws_secret_access_key="testing"
    )


def test_sqs_identifier_only_publish_receive_and_ack():
    settings = get_settings()
    settings.discovery_queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/qima-test"
    client = aws_test_client("sqs")
    queue = SQSQueue(client)
    with Stubber(client) as stub:
        stub.add_response(
            "send_message",
            {"MessageId": "message-1"},
            {
                "QueueUrl": settings.discovery_queue_url,
                "MessageBody": '{"job_id": "job-1", "agent_type": "SOURCING", "schema_version": 1}',
            },
        )
        stub.add_response(
            "receive_message",
            {
                "Messages": [
                    {
                        "MessageId": "message-1",
                        "ReceiptHandle": "receipt",
                        "Body": '{"job_id":"job-1","schema_version":1}',
                    }
                ]
            },
            {
                "QueueUrl": settings.discovery_queue_url,
                "MaxNumberOfMessages": 1,
                "WaitTimeSeconds": 20,
                "VisibilityTimeout": 120,
                "MessageSystemAttributeNames": ["ApproximateReceiveCount"],
            },
        )
        stub.add_response(
            "delete_message", {}, {"QueueUrl": settings.discovery_queue_url, "ReceiptHandle": "receipt"}
        )
        assert (
            queue.publish({"job_id": "job-1", "agent_type": "SOURCING", "schema_version": 1}) == "message-1"
        )
        assert queue.receive()[0]["MessageId"] == "message-1"
        queue.ack("receipt")
        stub.assert_no_pending_responses()


def test_s3_versioned_encrypted_write_and_read():
    get_settings().evidence_bucket = "qima-test-evidence"
    client = aws_test_client("s3")
    with Stubber(client) as stub:
        stub.add_response(
            "put_object",
            {"VersionId": "v1"},
            {
                "Bucket": "qima-test-evidence",
                "Key": "documents/id/file.txt",
                "Body": b"offer",
                "ContentType": "text/plain",
                "ServerSideEncryption": "AES256",
            },
        )
        stub.add_response(
            "get_object",
            {"Body": StreamingBody(io.BytesIO(b"offer"), 5)},
            {"Bucket": "qima-test-evidence", "Key": "documents/id/file.txt", "VersionId": "v1"},
        )
        provider = S3StorageProvider(client)
        assert provider.put("id/file.txt", b"offer", "text/plain") == "v1"
        assert provider.get("id/file.txt", "v1") == b"offer"
        stub.assert_no_pending_responses()


def test_scheduler_targets_queue_with_followup_id(monkeypatch):
    settings = get_settings()
    settings.discovery_queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/qima-test"
    settings.scheduler_role_arn = "arn:aws:iam::123456789012:role/test-scheduler"
    queue = aws_test_client("sqs")
    scheduler = aws_test_client("scheduler")
    monkeypatch.setattr("app.integrations.queue.aws_client", lambda service: queue)
    followup = SimpleNamespace(
        id="6f61cd3a-a426-48d1-90f7-8484d793fa92", due_at=datetime(2027, 1, 1, tzinfo=UTC)
    )
    with Stubber(queue) as qs, Stubber(scheduler) as ss:
        qs.add_response(
            "get_queue_attributes",
            {"Attributes": {"QueueArn": "arn:aws:sqs:us-east-1:123456789012:qima-test"}},
            {"QueueUrl": settings.discovery_queue_url, "AttributeNames": ["QueueArn"]},
        )
        ss.add_response(
            "create_schedule",
            {"ScheduleArn": "arn:aws:scheduler:us-east-1:123456789012:schedule/default/test"},
            {
                "Name": f"qima-followup-{followup.id}",
                "GroupName": "default",
                "ScheduleExpression": "at(2027-01-01T00:00:00)",
                "ScheduleExpressionTimezone": "UTC",
                "FlexibleTimeWindow": {"Mode": "OFF"},
                "ActionAfterCompletion": "DELETE",
                "Target": ANY,
                "ClientToken": followup.id,
            },
        )
        schedule_followup(followup, scheduler)
        ss.assert_no_pending_responses()


@pytest.mark.parametrize(
    "change",
    [{}, {"client_id": "wrong"}, {"token_use": "id"}, {"exp": 1}, {"iss": "https://malicious.example"}],
)
def test_cognito_signature_issuer_client_expiry_and_token_use(monkeypatch, change):
    settings = get_settings()
    settings.auth_mode = "cognito"
    settings.aws_region = "us-east-1"
    settings.cognito_user_pool_id = "us-east-1_test"
    settings.cognito_app_client_id = "test-client"
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(
        "app.auth.jwks_client",
        lambda: SimpleNamespace(
            get_signing_key_from_jwt=lambda token: SimpleNamespace(key=private.public_key())
        ),
    )
    claims = {
        "sub": "user-1",
        "iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_test",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=5),
        "token_use": "access",
        "client_id": "test-client",
        "cognito:groups": ["VIEWER", "untrusted-group"],
        **change,
    }
    token = jwt.encode(claims, private, algorithm="RS256")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    if change:
        with pytest.raises(HTTPException) as error:
            current_actor(credentials)
        assert error.value.status_code == 401
    else:
        assert current_actor(credentials).roles == {"VIEWER"}
