from typing import Protocol


class EmailProvider(Protocol):
    def send(self, draft_id: str, recipient: str, subject: str, body: str) -> str: ...


class MockEmailProvider:
    def send(self, draft_id: str, recipient: str, subject: str, body: str) -> str:
        # Stable across retries; this implementation performs no network operation.
        return f"mock-email-{draft_id}"


class GmailEmailProvider:
    def send(self, draft_id: str, recipient: str, subject: str, body: str) -> str:
        raise NotImplementedError("Requires reviewed OAuth integration and explicit real-send authorization")


class InstagramProvider(Protocol):
    def record_manual_send(self, draft_id: str, actor: str) -> str: ...


class ManualInstagramProvider:
    def record_manual_send(self, draft_id: str, actor: str) -> str:
        return f"manual-instagram-{draft_id}"


class OfficialMetaProvider:
    def send(self, *args, **kwargs):
        raise NotImplementedError("Automated cold DMs are not supported in V1")
