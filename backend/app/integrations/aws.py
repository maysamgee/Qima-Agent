from typing import Any

import boto3
from botocore.config import Config

from app.config import get_settings


def aws_client(service: str) -> Any:
    settings = get_settings()
    session: Any = boto3.Session(
        profile_name=settings.aws_profile or None, region_name=settings.aws_region or None
    )
    return session.client(
        service,
        config=Config(
            connect_timeout=5,
            read_timeout=settings.bedrock_request_timeout_seconds if service == "bedrock-runtime" else 25,
            retries={"max_attempts": 2, "mode": "standard"},
        ),
    )
