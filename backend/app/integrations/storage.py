import hashlib
import os
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from fastapi import HTTPException

from app.config import get_settings
from app.integrations.aws import aws_client

MAX_UPLOAD = 10 * 1024 * 1024
ALLOWED = {
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class StorageProvider(Protocol):
    def put(self, key: str, body: bytes, content_type: str) -> str | None: ...
    def get(self, key: str, version: str | None = None) -> bytes: ...


class LocalStorageProvider:
    def __init__(self, root=None):
        self.root = Path(root or get_settings().local_storage_path).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key):
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Invalid storage key")
        return path

    def put(self, key, body, content_type):
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Content-addressed immutable objects make retries safe.
        if path.exists():
            if hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(body).digest():
                raise ValueError("Existing immutable object failed integrity validation")
        else:
            temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
            with temporary.open("xb") as file:
                file.write(body)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
        return hashlib.sha256(body).hexdigest()

    def get(self, key, version=None):
        return self.path(key).read_bytes()


class S3StorageProvider:
    def __init__(self, client=None):
        self.client = client or aws_client("s3")
        self.bucket = get_settings().evidence_bucket

    def put(self, key, body, content_type):
        result = self.client.put_object(
            Bucket=self.bucket,
            Key=f"documents/{key}",
            Body=body,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )
        return result.get("VersionId")

    def get(self, key, version=None):
        kwargs = {"Bucket": self.bucket, "Key": f"documents/{key}"}
        if version:
            kwargs["VersionId"] = version
        response = self.client.get_object(**kwargs)
        try:
            data = response["Body"].read(MAX_UPLOAD + 1)
            if len(data) > MAX_UPLOAD:
                raise ValueError("Stored object exceeds allowed size")
            return data
        finally:
            response["Body"].close()


def storage_provider() -> StorageProvider:
    return LocalStorageProvider() if get_settings().storage_provider == "local" else S3StorageProvider()


def validate_upload(filename: str, data: bytes):
    safe_name = Path(filename.replace("\\", "/")).name
    extension = Path(safe_name).suffix.lower()
    if extension not in ALLOWED or not data or len(data) > MAX_UPLOAD:
        raise HTTPException(422, "Choose a nonempty CSV, TXT, PDF, DOCX or XLSX file up to 10 MiB")
    if extension == ".pdf" and not data.startswith(b"%PDF-"):
        raise HTTPException(422, "Invalid PDF signature")
    if extension in {".docx", ".xlsx"} and not data.startswith(b"PK\x03\x04"):
        raise HTTPException(422, "Invalid office document signature")
    if extension in {".txt", ".csv"}:
        try:
            text = data.decode("utf-8-sig")
            if "\x00" in text:
                raise ValueError()
        except (UnicodeDecodeError, ValueError):
            raise HTTPException(422, "Text documents must contain UTF-8 text") from None
    return safe_name[:255], extension, ALLOWED[extension]
