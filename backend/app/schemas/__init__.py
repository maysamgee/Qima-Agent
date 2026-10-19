from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class Mode(StrEnum):
    LEAD = "LEAD"
    SOURCING = "SOURCING"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchRequest(StrictModel):
    agent_type: Mode
    query: str = Field(min_length=5, max_length=1500)
    country: str = Field(default="", max_length=100)


class ToolArgs(StrictModel):
    query: str = Field(default="", max_length=1500)
    url: HttpUrl | None = None
    country: str = Field(default="", max_length=100)


class ToolCall(StrictModel):
    name: Literal[
        "web_search", "website_fetch", "instagram", "trade_show", "coffee_listing", "contact_enrichment"
    ]
    arguments: ToolArgs


class ResearchPlan(StrictModel):
    objective: str = Field(max_length=2000)
    queries: list[str] = Field(max_length=8)
    tool_calls: list[ToolCall] = Field(default_factory=list, max_length=8)
    complete: bool = False


class EvidenceInput(StrictModel):
    category: Literal[
        "website",
        "Instagram",
        "trade_show",
        "association",
        "coffee_listing",
        "external_market_mention",
        "contact",
        "product",
        "production",
        "buyer_activity",
        "supplier_activity",
        "network_relationship",
    ]
    claim: str = Field(min_length=1, max_length=1500)
    source_url: HttpUrl
    source_title: str = Field(max_length=255)
    evidence_summary: str = Field(max_length=2000)
    source_type: str = Field(default="public_web", max_length=50)
    published_at: datetime | None = None
    confidence: float = Field(ge=0, le=1)
    verification_status: Literal["UNVERIFIED", "CORROBORATED", "VERIFIED", "CONFLICTING"] = "UNVERIFIED"
    signals: list[str] = Field(default_factory=list, max_length=20)


class CandidateProfile(StrictModel):
    company_name: str = Field(min_length=1, max_length=255)
    entity_type: str = Field(min_length=1, max_length=100)
    country: str = Field(min_length=1, max_length=100)
    website_url: HttpUrl | None = None
    instagram_handle: str | None = Field(default=None, pattern=r"^@?[A-Za-z0-9_.]{1,30}$")
    company_bio: str = Field(default="", max_length=2000)
    product_summary: str = Field(default="", max_length=2000)
    email: str | None = Field(default=None, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    evidence: list[EvidenceInput] = Field(default_factory=list, max_length=40)
    missing_evidence: list[str] = Field(default_factory=list, max_length=20)
    demo: bool = False


class EvidenceProfile(StrictModel):
    candidates: list[CandidateProfile] = Field(max_length=25)


class LeadOutput(EvidenceProfile):
    buying_interest_summary: str = Field(default="", max_length=2000)


class SourcingOutput(EvidenceProfile):
    production_summary: str = Field(default="", max_length=2000)


class CandidateClassification(StrictModel):
    entity_type: str = Field(max_length=100)
    relevant: bool
    explanation: str = Field(max_length=2000)


class ToolResult(StrictModel):
    availability: Literal["AVAILABLE", "UNAVAILABLE", "NOT_FOUND", "MANUAL_REVIEW_REQUIRED"]
    provider: str
    fictional: bool = False
    items: list[dict] = Field(default_factory=list, max_length=50)
    note: str = ""


class OutreachOutput(StrictModel):
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1, max_length=6000)
    evidence_ids: list[str] = Field(default_factory=list)


class ReplyOutput(StrictModel):
    intent: Literal[
        "INTERESTED", "OFFER_RECEIVED", "NEEDS_INFORMATION", "FOLLOW_UP_LATER", "NOT_INTERESTED", "UNKNOWN"
    ]
    summary: str = Field(max_length=1000)
    sentiment: Literal["POSITIVE", "NEUTRAL", "NEGATIVE"] = "NEUTRAL"
    human_attention_required: bool = True
    recommended_next_action: str = Field(max_length=1000)
    followup_date_recommendation: datetime | None = None
    offer_document_indication: bool = False
    confidence: float = Field(ge=0, le=1)


class OfferOutput(StrictModel):
    supplier: str | None = None
    origin: str | None = None
    region: str | None = None
    lot: str | None = None
    process: str | None = None
    variety: str | None = None
    crop_year: str | None = None
    quantity: str | None = None
    unit: str | None = None
    price: str | None = None
    currency: str | None = None
    incoterm: str | None = None
    notes: str = "AI EXTRACTED — HUMAN REVIEW REQUIRED"


class ReviewRequest(StrictModel):
    action: Literal["APPROACH", "RESEARCH_MORE", "REJECT", "ARCHIVE", "MERGE_DUPLICATE"]
    notes: str = Field(default="", max_length=3000)
    merge_target_id: str | None = None


class DraftRequest(StrictModel):
    channel: Literal["EMAIL", "INSTAGRAM"] = "EMAIL"


class DraftEdit(StrictModel):
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1, max_length=6000)
    expected_version: int = Field(ge=1)


class VersionRequest(StrictModel):
    expected_version: int = Field(ge=1)


class ReplyRequest(StrictModel):
    body: str = Field(min_length=1, max_length=10000)


class FollowupRequest(StrictModel):
    due_at: datetime

    @field_validator("due_at")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError("Use a timezone-aware date")
        return value


class NoteRequest(StrictModel):
    notes: str = Field(min_length=1, max_length=3000)


class Criterion(StrictModel):
    key: str = Field(pattern=r"^[a-z_]{2,60}$")
    label: str = Field(min_length=1, max_length=100)
    weight: int = Field(gt=0, le=100)
    signals: list[str] = Field(min_length=1, max_length=15)


class PolicyRequest(StrictModel):
    agent_type: Mode
    criteria: list[Criterion] = Field(min_length=1, max_length=15)

    @model_validator(mode="after")
    def weights(self):
        if sum(c.weight for c in self.criteria) != 100:
            raise ValueError("Weights must total 100")
        if len({c.key for c in self.criteria}) != len(self.criteria):
            raise ValueError("Criterion keys must be unique")
        return self
