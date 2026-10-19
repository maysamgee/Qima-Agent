from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Record:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class User(Record, Base):
    __tablename__ = "users"
    subject: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    roles: Mapped[list] = mapped_column(JSON, default=list)


class SearchJob(Record, Base):
    __tablename__ = "search_jobs"
    __table_args__ = (CheckConstraint("agent_type IN ('LEAD','SOURCING')"),)
    agent_type: Mapped[str] = mapped_column(String(20))
    query: Mapped[str] = mapped_column(Text)
    country: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[str] = mapped_column(String(30), default="QUEUED", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    requested_by: Mapped[str] = mapped_column(String(255))
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SearchJobStep(Record, Base):
    __tablename__ = "search_job_steps"
    __table_args__ = (UniqueConstraint("job_id", "name"),)
    job_id: Mapped[str] = mapped_column(ForeignKey("search_jobs.id"), index=True)
    name: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_count: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    output_reference: Mapped[str | None] = mapped_column(String(255))
    checkpoint_metadata: Mapped[dict] = mapped_column(JSON, default=dict)


class OutboxEvent(Record, Base):
    __tablename__ = "outbox_events"
    event_key: Mapped[str] = mapped_column(String(200), unique=True)
    event_type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSON)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(Text)


class ProcessedQueueMessage(Record, Base):
    __tablename__ = "processed_queue_messages"
    message_key: Mapped[str] = mapped_column(String(200), unique=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("search_jobs.id"))


class Candidate(Record, Base):
    __tablename__ = "candidates"
    __table_args__ = (CheckConstraint("domain_mode IN ('LEAD','SOURCING')"),)
    domain_mode: Mapped[str] = mapped_column(String(20), index=True)
    identity_key: Mapped[str] = mapped_column(String(500), unique=True)
    company_name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    entity_type: Mapped[str] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(100))
    origin_country: Mapped[str | None] = mapped_column(String(100))
    target_market: Mapped[str | None] = mapped_column(String(100))
    website_url: Mapped[str | None] = mapped_column(String(2048))
    normalized_domain: Mapped[str | None] = mapped_column(String(255), index=True)
    instagram_handle: Mapped[str | None] = mapped_column(String(100))
    company_bio: Mapped[str] = mapped_column(Text, default="")
    product_summary: Mapped[str] = mapped_column(Text, default="")
    verification_status: Mapped[str] = mapped_column(String(30), default="PENDING")
    current_status: Mapped[str] = mapped_column(String(40), default="WAITING_FOR_REVIEW", index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    merged_into_id: Mapped[str | None] = mapped_column(ForeignKey("candidates.id"))
    risk_flags: Mapped[list] = mapped_column(JSON, default=list)
    missing_evidence: Mapped[list] = mapped_column(JSON, default=list)
    demo: Mapped[bool] = mapped_column(Boolean, default=False)


class JobCandidate(Record, Base):
    __tablename__ = "job_candidates"
    __table_args__ = (UniqueConstraint("job_id", "candidate_id"),)
    job_id: Mapped[str] = mapped_column(ForeignKey("search_jobs.id"))
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"))


class CandidateAlias(Record, Base):
    __tablename__ = "candidate_aliases"
    __table_args__ = (UniqueConstraint("candidate_id", "alias"),)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"))
    alias: Mapped[str] = mapped_column(String(500))


class CandidateEvidence(Record, Base):
    __tablename__ = "candidate_evidence"
    __table_args__ = (CheckConstraint("confidence >= 0 AND confidence <= 1"),)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    category: Mapped[str] = mapped_column(String(50))
    claim: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(String(2048))
    source_domain: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(50))
    source_title: Mapped[str] = mapped_column(String(255))
    evidence_summary: Mapped[str] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    freshness_status: Mapped[str] = mapped_column(String(30), default="UNKNOWN")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    verification_status: Mapped[str] = mapped_column(String(30), default="UNVERIFIED")
    collection_method: Mapped[str] = mapped_column(String(50))
    agent_type: Mapped[str] = mapped_column(String(20))
    job_id: Mapped[str | None] = mapped_column(ForeignKey("search_jobs.id"))
    raw_metadata: Mapped[dict] = mapped_column(JSON, default=dict)


class ContactPoint(Record, Base):
    __tablename__ = "contact_points"
    __table_args__ = (UniqueConstraint("candidate_id", "kind", "value"),)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    value: Mapped[str] = mapped_column(String(320))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    source_url: Mapped[str | None] = mapped_column(String(2048))


class SocialActivitySnapshot(Record, Base):
    __tablename__ = "social_activity_snapshots"
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"))
    availability: Mapped[str] = mapped_column(String(40))
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class ScoringPolicy(Record, Base):
    __tablename__ = "scoring_policies"
    __table_args__ = (UniqueConstraint("agent_type", "version"),)
    agent_type: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(Integer)
    criteria: Mapped[list] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(255), default="system")


class ScoringResult(Record, Base):
    __tablename__ = "scoring_results"
    __table_args__ = (
        UniqueConstraint("candidate_id", "policy_id", "evidence_hash"),
        CheckConstraint("total >= 0 AND total <= 100"),
    )
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), index=True)
    policy_id: Mapped[str] = mapped_column(ForeignKey("scoring_policies.id"))
    rubric_version: Mapped[int] = mapped_column(Integer)
    evidence_hash: Mapped[str] = mapped_column(String(64))
    total: Mapped[int] = mapped_column(Integer)
    band: Mapped[str] = mapped_column(String(60))
    evidence_confidence: Mapped[str] = mapped_column(String(20))
    confidence_explanation: Mapped[str] = mapped_column(Text)
    breakdown: Mapped[list] = mapped_column(JSON)


class HumanReview(Record, Base):
    __tablename__ = "human_reviews"
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"))
    reviewer: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(40))
    notes: Mapped[str] = mapped_column(Text, default="")
    before_state: Mapped[str] = mapped_column(String(40))
    after_state: Mapped[str] = mapped_column(String(40))
    request_key: Mapped[str] = mapped_column(String(200), unique=True)


class OutreachCase(Record, Base):
    __tablename__ = "outreach_cases"
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), unique=True)
    status: Mapped[str] = mapped_column(String(40), default="DRAFTING")


class OutreachDraft(Record, Base):
    __tablename__ = "outreach_drafts"
    case_id: Mapped[str] = mapped_column(ForeignKey("outreach_cases.id"))
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), index=True)
    channel: Mapped[str] = mapped_column(String(20))
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    agent_type: Mapped[str] = mapped_column(String(20))
    prompt_version: Mapped[str] = mapped_column(String(30))
    model_id: Mapped[str] = mapped_column(String(255))
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(default=1)
    approval_status: Mapped[str] = mapped_column(String(30), default="PENDING")
    request_key: Mapped[str] = mapped_column(String(200), unique=True)


class DraftRevision(Record, Base):
    __tablename__ = "draft_revisions"
    __table_args__ = (UniqueConstraint("draft_id", "version"),)
    draft_id: Mapped[str] = mapped_column(ForeignKey("outreach_drafts.id"))
    version: Mapped[int] = mapped_column(Integer)
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(255))


class Approval(Record, Base):
    __tablename__ = "approvals"
    __table_args__ = (UniqueConstraint("draft_id", "draft_version"),)
    draft_id: Mapped[str] = mapped_column(ForeignKey("outreach_drafts.id"))
    draft_version: Mapped[int] = mapped_column(Integer)
    actor: Mapped[str] = mapped_column(String(255))
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConversationThread(Record, Base):
    __tablename__ = "conversation_threads"
    __table_args__ = (UniqueConstraint("candidate_id", "channel"),)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"))
    channel: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(40), default="OPEN")


class Message(Record, Base):
    __tablename__ = "messages"
    thread_id: Mapped[str] = mapped_column(ForeignKey("conversation_threads.id"))
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), index=True)
    draft_id: Mapped[str | None] = mapped_column(ForeignKey("outreach_drafts.id"), unique=True)
    direction: Mapped[str] = mapped_column(String(20))
    body: Mapped[str] = mapped_column(Text)
    provider_message_id: Mapped[str] = mapped_column(String(255), unique=True)
    request_key: Mapped[str] = mapped_column(String(200), unique=True)
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    actor: Mapped[str] = mapped_column(String(255))
    classification: Mapped[dict] = mapped_column(JSON, default=dict)


class Followup(Record, Base):
    __tablename__ = "followups"
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(30), default="SCHEDULED")
    request_key: Mapped[str] = mapped_column(String(200), unique=True)
    draft_id: Mapped[str | None] = mapped_column(ForeignKey("outreach_drafts.id"))
    baseline_reply_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id"))


class Document(Record, Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("candidate_id", "sha256"),)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    storage_key: Mapped[str] = mapped_column(String(500))
    storage_version: Mapped[str | None] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(40), default="HUMAN_REVIEW_REQUIRED")


class Offer(Record, Base):
    __tablename__ = "offers"
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), unique=True)
    extracted_data: Mapped[dict] = mapped_column(JSON)
    review_status: Mapped[str] = mapped_column(String(40), default="HUMAN_REVIEW_REQUIRED")
    reviewed_by: Mapped[str | None] = mapped_column(String(255))


class Handoff(Record, Base):
    __tablename__ = "handoffs"
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), unique=True)
    summary: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(255))
    request_key: Mapped[str] = mapped_column(String(200), unique=True)


class AuditEvent(Record, Base):
    __tablename__ = "audit_events"
    actor: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(100), index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    correlation_id: Mapped[str | None] = mapped_column(String(100))


class DoNotContactEntry(Record, Base):
    __tablename__ = "do_not_contact_entries"
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), unique=True)
    reason: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(255))
