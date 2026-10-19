import hashlib
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError

from app.config import get_settings
from app.integrations.discovery import MockInstagramEvidenceProvider, UnconfiguredProvider, search_provider
from app.integrations.safe_fetch import SafeHTTPWebsiteFetcher
from app.schemas import ResearchPlan, ToolResult


class ControlledToolRuntime:
    def __init__(self, model, audit):
        self.model = model
        self.audit = audit
        self.settings = get_settings()

    def execute(self, agent, query: str, country: str):
        deadline = time.monotonic() + self.settings.job_timeout_seconds
        seen: set[str] = set()
        results: list[dict] = []
        calls = 0
        for _ in range(self.settings.bedrock_max_tool_iterations):
            if time.monotonic() >= deadline:
                raise TimeoutError("Research time budget exceeded")
            plan = ResearchPlan.model_validate(
                self.model.create_research_plan(agent, query, country, results)
            )
            self.audit("model.plan", {"objective": plan.objective, **self.model.last_usage})
            if plan.complete or not plan.tool_calls:
                break
            progressed = False
            for call in plan.tool_calls:
                if calls >= self.settings.bedrock_max_tool_iterations:
                    break
                fingerprint = hashlib.sha256(call.model_dump_json().encode()).hexdigest()
                if fingerprint in seen:
                    self.audit("tool.duplicate_skipped", {"tool": call.name, "fingerprint": fingerprint})
                    continue
                seen.add(fingerprint)
                progressed = True
                calls += 1
                started = time.monotonic()
                allowed = {
                    "web_search": lambda: search_provider().search(agent.agent_type, call.arguments),
                    "website_fetch": lambda: SafeHTTPWebsiteFetcher().fetch(str(call.arguments.url)),
                    "instagram": lambda: MockInstagramEvidenceProvider().collect(call.arguments),
                    "trade_show": lambda: UnconfiguredProvider("trade_show").collect(call.arguments),
                    "coffee_listing": lambda: UnconfiguredProvider("coffee_listing").collect(call.arguments),
                    "contact_enrichment": lambda: UnconfiguredProvider("contact_enrichment").collect(
                        call.arguments
                    ),
                }
                pool = ThreadPoolExecutor(max_workers=1)
                try:
                    future = pool.submit(allowed[call.name])
                    result = ToolResult.model_validate(
                        future.result(
                            timeout=max(
                                0.01, min(self.settings.tool_timeout_seconds, deadline - time.monotonic())
                            )
                        )
                    )
                except Exception as exc:
                    result = ToolResult(
                        availability="UNAVAILABLE",
                        provider=call.name,
                        note=type(exc).__name__ + ": source unavailable; not a negative business signal.",
                    )
                finally:
                    pool.shutdown(wait=False, cancel_futures=True)
                results.append(result.model_dump(mode="json"))
                self.audit(
                    "tool.result",
                    {
                        "tool": call.name,
                        "arguments": call.arguments.model_dump(mode="json"),
                        "availability": result.availability,
                        "provider": result.provider,
                        "latency_ms": round((time.monotonic() - started) * 1000),
                        "fingerprint": fingerprint,
                    },
                )
            if not progressed:
                break
        if time.monotonic() >= deadline:
            raise TimeoutError("Research time budget exceeded")
        profile = self.model.extract_structured_evidence(agent, results)

        # Prevent invented provenance. Only URLs actually supplied by tools are accepted.
        def source_urls(value):
            if isinstance(value, dict):
                return {str(v).rstrip("/") for k, v in value.items() if k == "source_url"} | set().union(
                    *(source_urls(v) for v in value.values())
                )
            if isinstance(value, list):
                return set().union(*(source_urls(v) for v in value))
            return set()

        supplied = source_urls(results)
        for candidate in profile.candidates:
            candidate.demo = self.settings.search_provider == "mock"
            for evidence in candidate.evidence:
                if str(evidence.source_url).rstrip("/") not in supplied:
                    raise ValueError("Model returned unsupported source provenance")
                if not candidate.demo:
                    evidence.verification_status = "UNVERIFIED"
        self.audit("model.extraction", {"candidate_count": len(profile.candidates), **self.model.last_usage})
        # Raw fetched pages are deliberately not checkpointed.
        return profile, [{k: v for k, v in r.items() if k != "items"} for r in results]
