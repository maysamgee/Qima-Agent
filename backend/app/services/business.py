import hashlib
import json
import logging
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session

from app.agents import get_agent
from app.ai.model import model_service
from app.auth import Actor, authorize
from app.integrations.outreach import ManualInstagramProvider, MockEmailProvider
from app.models import (
    Approval,
    AuditEvent,
    Candidate,
    CandidateAlias,
    CandidateEvidence,
    ContactPoint,
    ConversationThread,
    DoNotContactEntry,
    DraftRevision,
    Followup,
    Handoff,
    HumanReview,
    Message,
    OutreachCase,
    OutreachDraft,
    ScoringResult,
    utcnow,
)
from app.observability import correlation_id
from app.schemas import ReviewRequest
from app.scoring import calculate


def serialize(row):
    return {column.key: getattr(row, column.key) for column in inspect(row).mapper.column_attrs}


def audit(db: Session, actor: str, action: str, entity, details=None):
    fields = details or {}
    logging.getLogger("qima.workflow").info(
        json.dumps(
            {
                "event": action,
                "correlation_id": correlation_id.get(),
                "job_id": entity.id if entity.__tablename__ == "search_jobs" else None,
                "candidate_id": entity.id
                if entity.__tablename__ == "candidates"
                else getattr(entity, "candidate_id", None),
                "user_id": actor,
                "agent_type": getattr(entity, "agent_type", getattr(entity, "domain_mode", None)),
                "workflow_step": fields.get("step"),
                "provider": fields.get("provider"),
                "attempt": fields.get("attempt"),
                "status": fields.get("status"),
                "latency_ms": fields.get("latency_ms"),
                "error_type": fields.get("error_type"),
            }
        )
    )
    db.add(
        AuditEvent(
            actor=actor,
            action=action,
            entity_type=entity.__tablename__,
            entity_id=entity.id,
            details=fields,
            correlation_id=correlation_id.get(),
        )
    )


def request_key(scope: str, actor: Actor, value: str) -> str:
    if not value or len(value) > 128:
        raise HTTPException(400, "An Idempotency-Key of 1–128 characters is required")
    return hashlib.sha256(f"{actor.id}:{scope}:{value}".encode()).hexdigest()


def get_candidate(db: Session, candidate_id: str, lock=False) -> Candidate:
    stmt = select(Candidate).where(Candidate.id == candidate_id)
    row = db.scalar(stmt.with_for_update() if lock else stmt)
    if not row:
        raise HTTPException(404, "Candidate not found")
    return row


def can_contact(db: Session, candidate: Candidate, *, for_review=False):
    if (
        candidate.archived_at
        or candidate.merged_into_id
        or candidate.current_status == "DO_NOT_CONTACT"
        or (not for_review and candidate.current_status in {"REJECTED", "RESEARCH_MORE", "NOT_INTERESTED"})
    ):
        raise HTTPException(409, "Candidate is not eligible for outreach")
    if db.scalar(select(DoNotContactEntry).where(DoNotContactEntry.candidate_id == candidate.id)):
        raise HTTPException(409, "Do-not-contact restriction is active")
    if any(flag.startswith("PROBABLE_DUPLICATE") for flag in candidate.risk_flags):
        raise HTTPException(409, "Resolve the probable duplicate before outreach")


def ensure_approached(db: Session, candidate: Candidate):
    can_contact(db, candidate)
    review = db.scalar(
        select(HumanReview)
        .where(HumanReview.candidate_id == candidate.id)
        .order_by(HumanReview.created_at.desc())
    )
    if not review or review.action != "APPROACH":
        raise HTTPException(409, "A human must approve approaching this candidate first")


def review_candidate(db: Session, candidate_id: str, data: ReviewRequest, actor: Actor, key: str):
    existing = db.scalar(select(HumanReview).where(HumanReview.request_key == key))
    if existing:
        return existing
    candidate = get_candidate(db, candidate_id, True)
    authorize(actor, candidate.domain_mode, review=True)
    before = candidate.current_status
    states = {
        "APPROACH": "APPROVED_FOR_OUTREACH",
        "RESEARCH_MORE": "RESEARCH_MORE",
        "REJECT": "REJECTED",
        "ARCHIVE": "ARCHIVED",
        "MERGE_DUPLICATE": "MERGED",
    }
    if candidate.archived_at:
        raise HTTPException(409, "Archived candidates cannot be changed through review")
    if data.action == "APPROACH":
        can_contact(db, candidate, for_review=True)
        latest_score = db.scalar(
            select(ScoringResult)
            .where(ScoringResult.candidate_id == candidate.id)
            .order_by(ScoringResult.created_at.desc())
        )
        if not latest_score:
            raise HTTPException(409, "Complete evidence scoring before approving outreach")
        if latest_score.evidence_confidence in {"LOW", "INSUFFICIENT"} and len(data.notes.strip()) < 20:
            raise HTTPException(
                409,
                "Low-confidence candidates require notes explaining the human research supporting this decision",
            )
    if data.action == "MERGE_DUPLICATE":
        if not data.merge_target_id or data.merge_target_id == candidate.id:
            raise HTTPException(422, "Choose a different merge target")
        target = get_candidate(db, data.merge_target_id, True)
        if target.domain_mode != candidate.domain_mode or target.archived_at:
            raise HTTPException(409, "Merge target must be active in the same business mode")
        # Keep original records and provenance. Alias directs future discovery to the survivor.
        candidate.merged_into_id = target.id
        db.add(CandidateAlias(candidate_id=target.id, alias=candidate.identity_key))
        for e in db.scalars(select(CandidateEvidence).where(CandidateEvidence.candidate_id == candidate.id)):
            e.candidate_id = target.id
            e.raw_metadata = {**e.raw_metadata, "merged_from_candidate_id": candidate.id}
        for cp in db.scalars(select(ContactPoint).where(ContactPoint.candidate_id == candidate.id)):
            if not db.scalar(
                select(ContactPoint).where(
                    ContactPoint.candidate_id == target.id,
                    ContactPoint.kind == cp.kind,
                    ContactPoint.value == cp.value,
                )
            ):
                db.add(
                    ContactPoint(
                        candidate_id=target.id,
                        kind=cp.kind,
                        value=cp.value,
                        verified=cp.verified,
                        source_url=cp.source_url,
                    )
                )
        target.risk_flags = [f for f in target.risk_flags if f != f"PROBABLE_DUPLICATE:{candidate.id}"]
        if db.scalar(
            select(DoNotContactEntry).where(DoNotContactEntry.candidate_id == candidate.id)
        ) and not db.scalar(select(DoNotContactEntry).where(DoNotContactEntry.candidate_id == target.id)):
            db.add(
                DoNotContactEntry(
                    candidate_id=target.id, actor=actor.id, reason="Inherited from merged candidate"
                )
            )
        audit(db, actor.id, "candidate.merge_received", target, {"source_id": candidate.id})
        previous_target_status = target.current_status
        target.current_status = "WAITING_FOR_REVIEW"
        db.add(
            HumanReview(
                candidate_id=target.id,
                reviewer=actor.id,
                action="RESEARCH_MORE",
                notes="Merged evidence requires a fresh approach decision.",
                before_state=previous_target_status,
                after_state=target.current_status,
                request_key=f"merge-review:{candidate.id}:{target.id}",
            )
        )
        db.flush()
        calculate(db, target)
    if data.action in {"ARCHIVE", "MERGE_DUPLICATE"}:
        candidate.archived_at = utcnow()
    candidate.current_status = states[data.action]
    row = HumanReview(
        candidate_id=candidate.id,
        reviewer=actor.id,
        action=data.action,
        notes=data.notes,
        before_state=before,
        after_state=candidate.current_status,
        request_key=key,
    )
    db.add(row)
    audit(
        db,
        actor.id,
        "candidate.review",
        candidate,
        {
            "action": data.action,
            "before": before,
            "after": candidate.current_status,
            "notes": data.notes,
            "merge_target_id": data.merge_target_id,
        },
    )
    db.flush()
    return row


def create_draft(db: Session, candidate: Candidate, channel: str, actor: Actor, key: str):
    existing = db.scalar(select(OutreachDraft).where(OutreachDraft.request_key == key))
    if existing:
        return existing
    ensure_approached(db, candidate)
    case = db.scalar(select(OutreachCase).where(OutreachCase.candidate_id == candidate.id))
    if not case:
        case = OutreachCase(candidate_id=candidate.id)
        db.add(case)
        db.flush()
    evidence = list(
        db.scalars(select(CandidateEvidence).where(CandidateEvidence.candidate_id == candidate.id))
    )
    model = model_service()
    agent = get_agent(candidate.domain_mode)
    result = model.generate_outreach(agent, serialize(candidate), [serialize(e) for e in evidence], channel)
    if not set(result.evidence_ids).issubset({e.id for e in evidence}):
        raise HTTPException(422, "Draft references unknown evidence")
    draft = OutreachDraft(
        case_id=case.id,
        candidate_id=candidate.id,
        channel=channel,
        subject=result.subject,
        body=result.body,
        agent_type=candidate.domain_mode,
        prompt_version=agent.prompt_version,
        model_id=model.model_id,
        evidence_ids=result.evidence_ids,
        request_key=key,
    )
    db.add(draft)
    db.flush()
    db.add(
        DraftRevision(draft_id=draft.id, version=1, subject=draft.subject, body=draft.body, actor=actor.id)
    )
    audit(
        db,
        actor.id,
        "draft.created",
        draft,
        {"model": model.model_id, "channel": channel, "usage": model.last_usage},
    )
    return draft


def get_draft(db, draft_id, actor, review=False):
    draft = db.scalar(select(OutreachDraft).where(OutreachDraft.id == draft_id).with_for_update())
    if not draft:
        raise HTTPException(404, "Draft not found")
    candidate = get_candidate(db, draft.candidate_id, True)
    authorize(actor, candidate.domain_mode, review=review)
    return draft, candidate


def edit_draft(db, draft_id, data, actor):
    draft, candidate = get_draft(db, draft_id, actor)
    ensure_approached(db, candidate)
    if draft.version != data.expected_version or draft.approval_status == "SENT":
        raise HTTPException(409, "Draft changed or was already sent; reload it")
    for approval in db.scalars(
        select(Approval).where(Approval.draft_id == draft.id, Approval.invalidated_at.is_(None))
    ):
        approval.invalidated_at = utcnow()
    draft.version += 1
    draft.subject, draft.body = data.subject, data.body
    draft.approval_status = "PENDING"
    db.add(
        DraftRevision(
            draft_id=draft.id, version=draft.version, subject=draft.subject, body=draft.body, actor=actor.id
        )
    )
    audit(db, actor.id, "draft.edited_approval_invalidated", draft, {"version": draft.version})
    return draft


def approve_draft(db, draft_id, version, actor):
    draft, candidate = get_draft(db, draft_id, actor, review=True)
    ensure_approached(db, candidate)
    if draft.version != version or draft.approval_status == "SENT":
        raise HTTPException(409, "Draft version is stale or already sent")
    existing = db.scalar(
        select(Approval).where(Approval.draft_id == draft.id, Approval.draft_version == version)
    )
    if not existing:
        db.add(Approval(draft_id=draft.id, draft_version=version, actor=actor.id))
    draft.approval_status = "APPROVED"
    audit(db, actor.id, "draft.approved", draft, {"version": version})
    return draft


def get_thread(db, candidate_id, channel):
    thread = db.scalar(
        select(ConversationThread).where(
            ConversationThread.candidate_id == candidate_id, ConversationThread.channel == channel
        )
    )
    if not thread:
        thread = ConversationThread(candidate_id=candidate_id, channel=channel)
        db.add(thread)
        db.flush()
    return thread


def send_draft(db, draft_id, version, actor, key, manual=False):
    draft, candidate = get_draft(db, draft_id, actor, review=True)
    existing = db.scalar(select(Message).where(Message.draft_id == draft.id))
    if existing:
        return existing
    ensure_approached(db, candidate)
    approval = db.scalar(
        select(Approval).where(
            Approval.draft_id == draft.id,
            Approval.draft_version == version,
            Approval.invalidated_at.is_(None),
        )
    )
    if draft.version != version or not approval or draft.approval_status != "APPROVED":
        raise HTTPException(409, "Current draft needs human approval")
    if (draft.channel == "INSTAGRAM") != manual:
        raise HTTPException(409, "Instagram first-touch must be recorded manually")
    if manual:
        provider_id = ManualInstagramProvider().record_manual_send(draft.id, actor.id)
    else:
        contact = db.scalar(
            select(ContactPoint).where(
                ContactPoint.candidate_id == candidate.id, ContactPoint.kind == "EMAIL"
            )
        )
        if not contact:
            raise HTTPException(409, "An email contact is required for simulated email")
        provider_id = MockEmailProvider().send(draft.id, contact.value, draft.subject, draft.body)
    thread = get_thread(db, candidate.id, draft.channel)
    thread.status = "WAITING_FOR_REPLY"
    message = Message(
        candidate_id=candidate.id,
        thread_id=thread.id,
        draft_id=draft.id,
        direction="OUTBOUND",
        body=draft.body,
        provider_message_id=provider_id,
        request_key=key,
        simulated=not manual,
        actor=actor.id,
    )
    db.add(message)
    draft.approval_status = "SENT"
    candidate.current_status = "CONTACTED"
    audit(
        db,
        actor.id,
        "outreach.manual_send_recorded" if manual else "outreach.simulated_no_email_sent",
        draft,
        {"version": version, "provider_id": provider_id},
    )
    db.flush()
    return message


def simulate_reply(db, candidate, body, actor, key):
    existing = db.scalar(select(Message).where(Message.request_key == key))
    if existing:
        return existing
    if not db.scalar(
        select(Message).where(Message.candidate_id == candidate.id, Message.direction == "OUTBOUND")
    ):
        raise HTTPException(409, "Record an outbound message before simulating a reply")
    thread = get_thread(db, candidate.id, "EMAIL")
    result = model_service().classify_reply(body)
    message = Message(
        candidate_id=candidate.id,
        thread_id=thread.id,
        direction="INBOUND",
        body=body,
        provider_message_id=f"mock-reply-{key}",
        request_key=key,
        simulated=True,
        actor=actor.id,
        classification=result.model_dump(mode="json"),
    )
    db.add(message)
    # Only backend-approved reply outcomes may affect an active candidate's stage.
    outcomes = {
        "INTERESTED": "INTERESTED",
        "OFFER_RECEIVED": "OFFER_RECEIVED",
        "NEEDS_INFORMATION": "NEEDS_INFORMATION",
        "FOLLOW_UP_LATER": "FOLLOW_UP_LATER",
        "NOT_INTERESTED": "NOT_INTERESTED",
        "UNKNOWN": "UNKNOWN",
    }
    if not candidate.archived_at and candidate.current_status != "DO_NOT_CONTACT":
        candidate.current_status = outcomes[result.intent]
    thread.status = "REPLIED"
    for followup in db.scalars(
        select(Followup).where(Followup.candidate_id == candidate.id, Followup.status == "SCHEDULED")
    ):
        followup.status = "CANCELLED_REPLY"
    if result.intent == "NOT_INTERESTED" and any(
        w in body.casefold() for w in ["unsubscribe", "do not contact", "stop contacting"]
    ):
        if not db.scalar(select(DoNotContactEntry).where(DoNotContactEntry.candidate_id == candidate.id)):
            db.add(
                DoNotContactEntry(
                    candidate_id=candidate.id, reason="Explicit opt-out in simulated reply", actor=actor.id
                )
            )
    audit(db, actor.id, "reply.simulated_and_classified", candidate, {"intent": result.intent})
    db.flush()
    return message


def trigger_followup(db, followup_id):
    followup = db.scalar(select(Followup).where(Followup.id == followup_id).with_for_update())
    if not followup or followup.status != "SCHEDULED":
        return True
    if followup.due_at.replace(tzinfo=UTC) > datetime.now(UTC):
        return False
    candidate = get_candidate(db, followup.candidate_id, True)
    latest = db.scalar(
        select(Message)
        .where(Message.candidate_id == candidate.id, Message.direction == "INBOUND")
        .order_by(Message.created_at.desc())
    )
    if latest and latest.id != followup.baseline_reply_id:
        followup.status = "CANCELLED_REPLY"
        return True
    try:
        ensure_approached(db, candidate)
    except HTTPException:
        followup.status = "CANCELLED_INELIGIBLE"
        return True
    draft = create_draft(
        db, candidate, "EMAIL", Actor("scheduler", "Scheduler", set()), f"followup:{followup.id}"
    )
    followup.draft_id = draft.id
    followup.status = "DRAFT_READY"
    audit(db, "scheduler", "followup.draft_requires_approval", followup)
    return True


def create_handoff(db, candidate, actor, key):
    existing = db.scalar(select(Handoff).where(Handoff.candidate_id == candidate.id))
    if existing:
        return existing
    can_contact(db, candidate)
    if candidate.current_status not in {"INTERESTED", "OFFER_RECEIVED", "NEEDS_INFORMATION"}:
        raise HTTPException(409, "Review an interested reply or offer before commercial handoff")
    handoff = Handoff(
        candidate_id=candidate.id,
        summary=f"{candidate.company_name} — {candidate.domain_mode}. {candidate.product_summary} Current outcome: {candidate.current_status}. Commercial terms and all AI-extracted offers require human verification.",
        actor=actor.id,
        request_key=key,
    )
    db.add(handoff)
    db.flush()
    audit(db, actor.id, "handoff.created", handoff)
    return handoff
