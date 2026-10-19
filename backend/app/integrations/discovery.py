from typing import Protocol

import httpx

from app.config import get_settings
from app.integrations.demo import demo_profiles
from app.schemas import ToolArgs, ToolResult


class WebSearchProvider(Protocol):
    def search(self, mode: str, args: ToolArgs) -> ToolResult: ...


class WebsiteFetchProvider(Protocol):
    def fetch(self, url: str) -> ToolResult: ...


class InstagramEvidenceProvider(Protocol):
    def collect(self, args: ToolArgs) -> ToolResult: ...


class TradeShowProvider(Protocol):
    def collect(self, args: ToolArgs) -> ToolResult: ...


class CoffeeListingProvider(Protocol):
    def collect(self, args: ToolArgs) -> ToolResult: ...


class ContactEnrichmentProvider(Protocol):
    def collect(self, args: ToolArgs) -> ToolResult: ...


class MockWebSearchProvider:
    def search(self, mode: str, args: ToolArgs) -> ToolResult:
        profiles = demo_profiles(mode, args.country, args.query)
        return ToolResult(
            availability="AVAILABLE" if profiles else "NOT_FOUND",
            provider="mock_search",
            fictional=True,
            items=[p.model_dump(mode="json") for p in profiles],
            note="Fictional demo data. No internet research was performed.",
        )


class MockInstagramEvidenceProvider:
    def collect(self, args: ToolArgs) -> ToolResult:
        return ToolResult(
            availability="MANUAL_REVIEW_REQUIRED",
            provider="mock_instagram",
            fictional=True,
            note="Instagram data is unavailable. This is not evidence of inactivity.",
        )


class UnconfiguredProvider:
    def __init__(self, name: str):
        self.name = name

    def collect(self, args: ToolArgs) -> ToolResult:
        return ToolResult(
            availability="UNAVAILABLE",
            provider=self.name,
            note="An approved provider is not configured. Human research may supply evidence.",
        )


class ApprovedAPIWebSearchProvider:
    """Vendor-neutral contract: POST query/mode/country; return ToolResult JSON.

    The administrator must review the vendor's terms and response provenance.
    The endpoint is deployment configuration, never an AI-selected URL.
    """

    def search(self, mode: str, args: ToolArgs) -> ToolResult:
        settings = get_settings()
        with httpx.Client(
            timeout=settings.tool_timeout_seconds, follow_redirects=False, trust_env=False
        ) as client:
            with client.stream(
                "POST",
                settings.search_api_url,
                headers={"Authorization": f"Bearer {settings.search_api_key}"},
                json={"query": args.query, "country": args.country, "agent_type": mode},
            ) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 1_000_000:
                        raise ValueError("Search response exceeds limit")
        result = ToolResult.model_validate_json(bytes(body))
        if result.fictional:
            raise ValueError("Production provider returned fictional results")
        return result


def search_provider() -> WebSearchProvider:
    return (
        MockWebSearchProvider()
        if get_settings().search_provider == "mock"
        else ApprovedAPIWebSearchProvider()
    )
