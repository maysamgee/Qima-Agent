import hashlib
import time
from contextlib import contextmanager

from sqlalchemy import select, text

from app.agents import get_agent
from app.agents.shared.runtime import ControlledToolRuntime
from app.ai.model import model_service
from app.config import get_settings
from app.database import get_engine, session_factory
from app.models import (
    Candidate,
    JobCandidate,
    OutboxEvent,
    ProcessedQueueMessage,
    SearchJob,
    SearchJobStep,
    SocialActivitySnapshot,
    utcnow,
)
from app.repositories import upsert_candidate
from app.schemas import EvidenceProfile
from app.scoring import calculate
from app.services.business import audit

STEPS = [
    "planning",
    "initial_discovery",
    "website_analysis",
    "instagram_analysis",
    "trade_show_analysis",
    "coffee_listing_analysis",
    "network_analysis",
    "contact_enrichment",
    "verification",
    "deduplication",
    "evidence_extraction",
    "scoring",
    "completed",
]
DONE = {"COMPLETED", "PARTIAL", "WAITING_FOR_REVIEW"}


def create_job(db, data, actor, key):
    from fastapi import HTTPException

    existing = db.scalar(select(SearchJob).where(SearchJob.idempotency_key == key))
    if existing:
        if (existing.agent_type, existing.query, existing.country) != (
            data.agent_type,
            data.query,
            data.country,
        ):
            raise HTTPException(409, "Idempotency key was already used for a different search")
        return existing
    job = SearchJob(
        agent_type=data.agent_type,
        query=data.query,
        country=data.country,
        idempotency_key=key,
        requested_by=actor.id,
    )
    db.add(job)
    db.flush()
    for name in STEPS:
        db.add(SearchJobStep(job_id=job.id, name=name))
    db.add(
        OutboxEvent(
            event_key=f"discovery:{job.id}",
            event_type="DISCOVERY",
            payload={"job_id": job.id, "agent_type": job.agent_type, "schema_version": 1},
        )
    )
    audit(db, actor.id, "job.created", job, {"agent_type": job.agent_type})
    return job


@contextmanager
def job_lock(job_id: str):
    engine = get_engine()
    if engine.dialect.name != "postgresql":
        yield True
        return
    lock_key = int.from_bytes(hashlib.sha256(job_id.encode()).digest()[:8], "big", signed=True)
    with engine.connect() as connection:
        acquired = connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key})
        try:
            yield acquired
        finally:
            if acquired:
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})


def process_job(job_id: str, message_key: str | None = None, fail_after_step: str | None = None):
    settings = get_settings()
    with job_lock(job_id) as acquired:
        if not acquired:
            return False
        with session_factory()() as db:
            job = db.get(SearchJob, job_id)
            if not job:
                return True
            if job.status in DONE:
                if message_key and not db.scalar(
                    select(ProcessedQueueMessage).where(ProcessedQueueMessage.message_key == message_key)
                ):
                    db.add(ProcessedQueueMessage(message_key=message_key, job_id=job_id))
                    db.commit()
                return True
            if job.status == "FAILED_PERMANENT":
                return False
            job.attempts += 1
            job.status = "RUNNING"
            job.heartbeat_at = utcnow()
            db.commit()
            agent = get_agent(job.agent_type)
            started = time.monotonic()
            try:
                for name in STEPS:
                    if time.monotonic() - started > settings.job_timeout_seconds:
                        raise TimeoutError("Job execution budget exceeded")
                    step = db.scalar(
                        select(SearchJobStep).where(
                            SearchJobStep.job_id == job_id, SearchJobStep.name == name
                        )
                    )
                    assert step is not None
                    if step.status in DONE:
                        continue
                    step.status = "RUNNING"
                    step.started_at = utcnow()
                    step.retry_count += 1
                    db.commit()
                    output, partial = execute_step(db, job, agent, name)
                    step.checkpoint_metadata = output
                    step.output_reference = f"search_job_steps:{step.id}"
                    step.completed_at = utcnow()
                    step.status = "PARTIAL" if partial else "COMPLETED"
                    step.last_error = None
                    job.heartbeat_at = utcnow()
                    audit(
                        db,
                        "worker",
                        "job.step_completed",
                        job,
                        {"step": name, "status": step.status, "attempt": job.attempts},
                    )
                    db.commit()
                    if name == fail_after_step:
                        # Simulates abrupt termination after a durable checkpoint, without error handling.
                        raise SystemExit("Injected worker termination")
                steps = list(db.scalars(select(SearchJobStep).where(SearchJobStep.job_id == job_id)))
                job.status = "PARTIAL" if any(s.status == "PARTIAL" for s in steps) else "COMPLETED"
                job.last_error = None
                if message_key:
                    db.add(ProcessedQueueMessage(message_key=message_key, job_id=job_id))
                audit(db, "worker", "job.finished", job, {"status": job.status, "attempt": job.attempts})
                db.commit()
                return True
            except Exception as exc:
                db.rollback()
                job = db.get(SearchJob, job_id)
                assert job is not None
                job.status = (
                    "FAILED_PERMANENT" if job.attempts >= settings.max_job_attempts else "FAILED_RETRYABLE"
                )
                job.last_error = type(exc).__name__ + ": processing failed; see correlated audit steps"
                if "step" in locals() and step is not None:
                    step.status = job.status
                    step.last_error = job.last_error
                audit(
                    db, "worker", "job.failed", job, {"error_type": type(exc).__name__, "status": job.status}
                )
                db.commit()
                return False


def execute_step(db, job, agent, name):
    def record(action, details):
        audit(db, "worker", action, job, details)

    if name == "planning":
        plan = model_service().create_research_plan(agent, job.query, job.country)
        return plan.model_dump(mode="json"), False
    if name == "initial_discovery":
        profile, statuses = ControlledToolRuntime(model_service(), record).execute(
            agent, job.query, job.country
        )
        return {"profile": profile.model_dump(mode="json"), "sources": statuses}, any(
            s["availability"] in {"UNAVAILABLE", "MANUAL_REVIEW_REQUIRED"} for s in statuses
        )
    source = db.scalar(
        select(SearchJobStep).where(SearchJobStep.job_id == job.id, SearchJobStep.name == "initial_discovery")
    )
    assert source is not None
    profile = EvidenceProfile.model_validate(
        {"candidates": source.checkpoint_metadata["profile"]["candidates"]}
    )
    if name in {
        "website_analysis",
        "coffee_listing_analysis",
        "contact_enrichment",
        "network_analysis",
        "trade_show_analysis",
        "instagram_analysis",
    }:
        category = {
            "website_analysis": "website",
            "coffee_listing_analysis": "coffee_listing",
            "contact_enrichment": "contact",
            "network_analysis": "network_relationship",
            "trade_show_analysis": "trade_show",
            "instagram_analysis": "Instagram",
        }[name]
        count = sum(1 for c in profile.candidates for e in c.evidence if e.category == category)
        available = count > 0
        return {
            "availability": "AVAILABLE"
            if available
            else "MANUAL_REVIEW_REQUIRED"
            if name == "instagram_analysis"
            else "UNAVAILABLE",
            "evidence_count": count,
            "note": "Inventory of collected evidence; absent evidence is unknown, never a negative business signal.",
        }, not available and bool(profile.candidates)
    if name == "verification":
        classifications = [
            model_service().classify_candidate(agent, c.model_dump(mode="json")).model_dump(mode="json")
            for c in profile.candidates
        ]
        return {
            "classifications": classifications,
            "verification": "Human identity verification pending; model classification is advisory.",
        }, False
    if name in {"deduplication", "evidence_extraction"}:
        ids, duplicates = [], 0
        for c in profile.candidates:
            candidate, duplicate = upsert_candidate(db, c, job.agent_type, job.id)
            ids.append(candidate.id)
            duplicates += int(duplicate)
            if not db.scalar(
                select(SocialActivitySnapshot).where(SocialActivitySnapshot.candidate_id == candidate.id)
            ):
                db.add(
                    SocialActivitySnapshot(
                        candidate_id=candidate.id,
                        availability="MANUAL_REVIEW_REQUIRED",
                        details={"note": "No activity inference made"},
                    )
                )
        return {"candidate_ids": ids, "existing_candidates_reused": duplicates}, False
    if name == "scoring":
        candidates = db.scalars(
            select(Candidate)
            .join(JobCandidate, JobCandidate.candidate_id == Candidate.id)
            .where(JobCandidate.job_id == job.id)
        )
        return {"score_ids": [calculate(db, c).id for c in candidates]}, False
    return {"ready_for_human_review": True}, False
