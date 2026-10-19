import hashlib
from datetime import UTC, datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.model import model_service
from app.auth import Actor, authorize, reader
from app.config import get_settings
from app.database import get_db
from app.integrations.storage import MAX_UPLOAD, storage_provider, validate_upload
from app.models import (
    AuditEvent,
    Candidate,
    CandidateEvidence,
    ContactPoint,
    Document,
    DoNotContactEntry,
    Followup,
    Handoff,
    HumanReview,
    JobCandidate,
    Message,
    Offer,
    OutboxEvent,
    OutreachDraft,
    ScoringPolicy,
    ScoringResult,
    SearchJob,
    SearchJobStep,
)
from app.schemas import (
    DraftEdit,
    DraftRequest,
    FollowupRequest,
    Mode,
    NoteRequest,
    OfferOutput,
    PolicyRequest,
    ReplyOutput,
    ReplyRequest,
    ReviewRequest,
    SearchRequest,
    VersionRequest,
)
from app.scoring import calculate
from app.services.business import (
    approve_draft,
    audit,
    can_contact,
    create_draft,
    create_handoff,
    edit_draft,
    get_candidate,
    request_key,
    review_candidate,
    send_draft,
    serialize,
    simulate_reply,
)
from app.workflow.discovery import create_job

router = APIRouter(prefix="/api")
DB = Annotated[Session, Depends(get_db)]
User = Annotated[Actor, Depends(reader)]
Key = Annotated[str, Header(alias="Idempotency-Key")]


@router.get("/config")
def config():
    s = get_settings()
    mode = (
        "FULL MOCK"
        if s.ai_provider == "mock" and s.queue_provider == "local"
        else "LOCAL + AWS DEV"
        if s.queue_provider == "sqs" or s.storage_provider == "s3"
        else "LOCAL + BEDROCK"
    )
    return {
        "environment": s.app_env,
        "auth_mode": s.auth_mode,
        "mode": mode if s.app_env in {"local", "test"} else s.app_env.upper(),
        "discovery": "MOCK DISCOVERY" if s.search_provider == "mock" else "APPROVED API DISCOVERY",
        "ai_provider": s.ai_provider,
        "email": "SIMULATED — NO REAL EMAIL SENT",
        "instagram": "MANUAL FIRST-TOUCH ONLY",
        "queue": s.queue_provider,
        "storage": s.storage_provider,
    }


@router.get("/me")
def me(actor: User):
    return {"id": actor.id, "name": actor.name, "roles": sorted(actor.roles)}


def candidate_summary(db, candidate):
    score = db.scalar(
        select(ScoringResult)
        .where(ScoringResult.candidate_id == candidate.id)
        .order_by(ScoringResult.created_at.desc())
    )
    return {**serialize(candidate), "score": serialize(score) if score else None}


@router.get("/dashboard")
def dashboard(db: DB, actor: User):
    counts = {
        status: count
        for status, count in db.execute(
            select(Candidate.current_status, func.count())
            .where(Candidate.archived_at.is_(None))
            .group_by(Candidate.current_status)
        ).all()
    }
    jobs = {
        status: count
        for status, count in db.execute(
            select(SearchJob.status, func.count()).group_by(SearchJob.status)
        ).all()
    }
    latest_scores = select(
        ScoringResult.candidate_id,
        ScoringResult.total,
        func.row_number()
        .over(partition_by=ScoringResult.candidate_id, order_by=ScoringResult.created_at.desc())
        .label("rank"),
    ).subquery()
    priority_count = db.scalar(
        select(func.count())
        .select_from(latest_scores)
        .join(Candidate, Candidate.id == latest_scores.c.candidate_id)
        .where(latest_scores.c.rank == 1, latest_scores.c.total >= 80, Candidate.archived_at.is_(None))
    )
    return {
        "candidates_found": sum(counts.values()),
        "high_priority_candidates": priority_count,
        "awaiting_review": counts.get("WAITING_FOR_REVIEW", 0),
        "approved_for_outreach": counts.get("APPROVED_FOR_OUTREACH", 0),
        "contacted": db.scalar(
            select(func.count(func.distinct(Message.candidate_id))).where(Message.direction == "OUTBOUND")
        ),
        "waiting_for_reply": counts.get("CONTACTED", 0),
        "interested": counts.get("INTERESTED", 0),
        "offers_received": counts.get("OFFER_RECEIVED", 0),
        "searches_in_progress": sum(jobs.get(s, 0) for s in ["QUEUED", "RUNNING", "FAILED_RETRYABLE"]),
        "failed_jobs": jobs.get("FAILED_PERMANENT", 0),
        "outbox_pending": db.scalar(
            select(func.count(OutboxEvent.id)).where(OutboxEvent.published_at.is_(None))
        ),
        "dlq_status": "See CloudWatch"
        if get_settings().queue_provider == "sqs"
        else "Local queue — no SQS DLQ",
    }


@router.post("/jobs", status_code=201)
def new_job(data: SearchRequest, db: DB, actor: User, key: Key):
    authorize(actor, data.agent_type)
    job = create_job(db, data, actor, request_key("search", actor, key))
    return serialize(job)


@router.get("/jobs")
def jobs(db: DB, actor: User):
    return [
        serialize(j) for j in db.scalars(select(SearchJob).order_by(SearchJob.created_at.desc()).limit(100))
    ]


@router.get("/jobs/{job_id}")
def job_detail(job_id: str, db: DB, actor: User):
    job = db.get(SearchJob, job_id)
    if not job:
        raise HTTPException(404, "Search not found")
    steps = list(
        db.scalars(
            select(SearchJobStep).where(SearchJobStep.job_id == job_id).order_by(SearchJobStep.created_at)
        )
    )
    candidates = db.scalars(
        select(Candidate)
        .join(JobCandidate, JobCandidate.candidate_id == Candidate.id)
        .where(JobCandidate.job_id == job_id)
    )
    return {
        **serialize(job),
        "steps": [serialize(s) for s in steps],
        "candidates": [candidate_summary(db, c) for c in candidates],
    }


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: str, db: DB, actor: User):
    authorize(actor, admin=True)
    job = db.scalar(select(SearchJob).where(SearchJob.id == job_id).with_for_update())
    if not job or job.status not in {"FAILED_PERMANENT", "FAILED_RETRYABLE"}:
        raise HTTPException(409, "Only failed searches can be retried")
    job.status = "QUEUED"
    job.attempts = 0
    event = OutboxEvent(
        event_key=f"retry:{job.id}:{datetime.now(UTC).isoformat()}",
        event_type="DISCOVERY",
        payload={"job_id": job.id, "agent_type": job.agent_type, "schema_version": 1},
    )
    db.add(event)
    audit(db, actor.id, "job.retry_requested", job)
    return serialize(job)


@router.get("/candidates")
def candidates(
    db: DB,
    actor: User,
    mode: Mode | None = None,
    archived: bool = False,
    limit: int = Query(100, ge=1, le=250),
):
    statement = select(Candidate).order_by(Candidate.created_at.desc()).limit(limit)
    if mode:
        statement = statement.where(Candidate.domain_mode == mode)
    if not archived:
        statement = statement.where(Candidate.archived_at.is_(None))
    return [candidate_summary(db, c) for c in db.scalars(statement)]


@router.get("/candidates/{candidate_id}")
def candidate_detail(candidate_id: str, db: DB, actor: User):
    candidate = get_candidate(db, candidate_id)
    result = candidate_summary(db, candidate)
    for name, model in [
        ("evidence", CandidateEvidence),
        ("contacts", ContactPoint),
        ("reviews", HumanReview),
        ("drafts", OutreachDraft),
        ("messages", Message),
        ("followups", Followup),
        ("documents", Document),
        ("offers", Offer),
        ("handoffs", Handoff),
        ("score_history", ScoringResult),
    ]:
        result[name] = [
            serialize(x)
            for x in db.scalars(
                select(model)
                .where(cast(Any, model).candidate_id == candidate_id)
                .order_by(cast(Any, model).created_at.desc())
            )
        ]
    result["do_not_contact"] = bool(
        db.scalar(select(DoNotContactEntry).where(DoNotContactEntry.candidate_id == candidate_id))
    )
    return result


@router.post("/candidates/{candidate_id}/review")
def review(candidate_id: str, data: ReviewRequest, db: DB, actor: User, key: Key):
    return serialize(
        review_candidate(db, candidate_id, data, actor, request_key(f"review:{candidate_id}", actor, key))
    )


@router.post("/candidates/{candidate_id}/resolve-duplicate")
def resolve_duplicate(candidate_id: str, data: NoteRequest, db: DB, actor: User):
    candidate = get_candidate(db, candidate_id, True)
    authorize(actor, candidate.domain_mode, review=True)
    candidate.risk_flags = [f for f in candidate.risk_flags if not f.startswith("PROBABLE_DUPLICATE")]
    audit(db, actor.id, "duplicate.reviewed_distinct", candidate, {"notes": data.notes})
    return serialize(candidate)


@router.post("/candidates/{candidate_id}/do-not-contact")
def suppress(candidate_id: str, data: NoteRequest, db: DB, actor: User):
    candidate = get_candidate(db, candidate_id, True)
    authorize(actor, candidate.domain_mode, review=True)
    if not db.scalar(select(DoNotContactEntry).where(DoNotContactEntry.candidate_id == candidate_id)):
        db.add(DoNotContactEntry(candidate_id=candidate_id, reason=data.notes, actor=actor.id))
    candidate.current_status = "DO_NOT_CONTACT"
    audit(db, actor.id, "candidate.do_not_contact", candidate, {"reason": data.notes})
    return serialize(candidate)


@router.post("/candidates/{candidate_id}/drafts")
def draft(candidate_id: str, data: DraftRequest, db: DB, actor: User, key: Key):
    candidate = get_candidate(db, candidate_id, True)
    authorize(actor, candidate.domain_mode)
    return serialize(
        create_draft(
            db,
            candidate,
            data.channel,
            actor,
            request_key(f"draft:{candidate_id}:{data.channel}", actor, key),
        )
    )


@router.patch("/drafts/{draft_id}")
def draft_edit(draft_id: str, data: DraftEdit, db: DB, actor: User):
    return serialize(edit_draft(db, draft_id, data, actor))


@router.post("/drafts/{draft_id}/approve")
def draft_approve(draft_id: str, data: VersionRequest, db: DB, actor: User):
    return serialize(approve_draft(db, draft_id, data.expected_version, actor))


@router.post("/drafts/{draft_id}/send")
def draft_send(draft_id: str, data: VersionRequest, db: DB, actor: User, key: Key):
    return serialize(
        send_draft(db, draft_id, data.expected_version, actor, request_key(f"send:{draft_id}", actor, key))
    )


@router.post("/drafts/{draft_id}/record-manual-send")
def manual_send(draft_id: str, data: VersionRequest, db: DB, actor: User, key: Key):
    return serialize(
        send_draft(
            db,
            draft_id,
            data.expected_version,
            actor,
            request_key(f"manual:{draft_id}", actor, key),
            manual=True,
        )
    )


@router.post("/candidates/{candidate_id}/replies")
def reply(candidate_id: str, data: ReplyRequest, db: DB, actor: User, key: Key):
    if get_settings().app_env == "prod":
        raise HTTPException(403, "Reply simulation is development-only")
    candidate = get_candidate(db, candidate_id, True)
    authorize(actor, candidate.domain_mode)
    return serialize(
        simulate_reply(db, candidate, data.body, actor, request_key(f"reply:{candidate_id}", actor, key))
    )


@router.patch("/messages/{message_id}/classification")
def correct_reply(message_id: str, data: ReplyOutput, db: DB, actor: User):
    message = db.get(Message, message_id)
    if not message or message.direction != "INBOUND":
        raise HTTPException(404, "Reply not found")
    candidate = get_candidate(db, message.candidate_id, True)
    authorize(actor, candidate.domain_mode, review=True)
    before = message.classification
    message.classification = data.model_dump(mode="json")
    if not candidate.archived_at and candidate.current_status != "DO_NOT_CONTACT":
        candidate.current_status = data.intent
    audit(
        db,
        actor.id,
        "reply.classification_corrected",
        message,
        {"before": before, "after": message.classification},
    )
    return serialize(message)


@router.post("/candidates/{candidate_id}/notes")
def thread_note(candidate_id: str, data: NoteRequest, db: DB, actor: User):
    candidate = get_candidate(db, candidate_id)
    authorize(actor, candidate.domain_mode)
    audit(db, actor.id, "conversation.note", candidate, {"notes": data.notes})
    return {"saved": True}


@router.post("/candidates/{candidate_id}/followups")
def followup(candidate_id: str, data: FollowupRequest, db: DB, actor: User, key: Key):
    candidate = get_candidate(db, candidate_id, True)
    authorize(actor, candidate.domain_mode)
    can_contact(db, candidate)
    idem = request_key(f"followup:{candidate_id}", actor, key)
    existing = db.scalar(select(Followup).where(Followup.request_key == idem))
    if existing:
        return serialize(existing)
    if data.due_at <= datetime.now(UTC):
        raise HTTPException(422, "Follow-up date must be in the future")
    last_reply = db.scalar(
        select(Message)
        .where(Message.candidate_id == candidate_id, Message.direction == "INBOUND")
        .order_by(Message.created_at.desc())
    )
    row = Followup(
        candidate_id=candidate_id,
        due_at=data.due_at.astimezone(UTC),
        baseline_reply_id=last_reply.id if last_reply else None,
        request_key=idem,
    )
    db.add(row)
    db.flush()
    db.add(
        OutboxEvent(
            event_key=f"followup:{row.id}",
            event_type="FOLLOWUP_SCHEDULE",
            payload={"followup_id": row.id, "schema_version": 1},
        )
    )
    audit(db, actor.id, "followup.scheduled", row)
    return serialize(row)


@router.get("/followups")
def followups(db: DB, actor: User):
    return [serialize(f) for f in db.scalars(select(Followup).order_by(Followup.due_at).limit(250))]


@router.post("/candidates/{candidate_id}/handoff")
def handoff(candidate_id: str, db: DB, actor: User, key: Key):
    candidate = get_candidate(db, candidate_id, True)
    authorize(actor, candidate.domain_mode, review=True)
    return serialize(create_handoff(db, candidate, actor, request_key(f"handoff:{candidate_id}", actor, key)))


@router.post("/candidates/{candidate_id}/documents")
def upload(candidate_id: str, file: UploadFile, db: DB, actor: User):
    candidate = get_candidate(db, candidate_id, True)
    authorize(actor, candidate.domain_mode)
    data = file.file.read(MAX_UPLOAD + 1)
    filename, extension, content_type = validate_upload(file.filename or "", data)
    digest = hashlib.sha256(data).hexdigest()
    existing = db.scalar(
        select(Document).where(Document.candidate_id == candidate_id, Document.sha256 == digest)
    )
    if existing:
        return serialize(existing)
    key = f"{candidate.id}/{digest}{extension}"
    version = storage_provider().put(key, data, content_type)
    document = Document(
        candidate_id=candidate.id,
        filename=filename,
        content_type=content_type,
        storage_key=key,
        storage_version=version,
        sha256=digest,
        size=len(data),
    )
    db.add(document)
    db.flush()
    extracted = (
        model_service().extract_offer(data.decode("utf-8-sig")[:16000])
        if extension in {".txt", ".csv"}
        else OfferOutput(
            notes="Metadata stored only; PDF and Office attachments require human review. No OCR or active document execution."
        )
    )
    db.add(
        Offer(
            candidate_id=candidate.id,
            document_id=document.id,
            extracted_data=extracted.model_dump(mode="json"),
        )
    )
    audit(
        db, actor.id, "document.stored_human_review_required", document, {"sha256": digest, "size": len(data)}
    )
    return serialize(document)


@router.get("/documents/{document_id}/download")
def download(document_id: str, db: DB, actor: User):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Document not found")
    return Response(
        storage_provider().get(document.storage_key, document.storage_version),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": "attachment; filename=document"
            + document.filename[document.filename.rfind(".") :],
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.patch("/offers/{offer_id}")
def review_offer(offer_id: str, data: OfferOutput, db: DB, actor: User):
    offer = db.get(Offer, offer_id)
    if not offer:
        raise HTTPException(404, "Offer not found")
    candidate = get_candidate(db, offer.candidate_id, True)
    authorize(actor, candidate.domain_mode, review=True)
    audit(
        db,
        actor.id,
        "offer.reviewed",
        offer,
        {"before": offer.extracted_data, "after": data.model_dump(mode="json")},
    )
    offer.extracted_data = data.model_dump(mode="json")
    offer.review_status = "HUMAN_REVIEWED"
    offer.reviewed_by = actor.id
    return serialize(offer)


@router.get("/policies")
def policies(db: DB, actor: User):
    return [
        serialize(p)
        for p in db.scalars(
            select(ScoringPolicy).order_by(ScoringPolicy.agent_type, ScoringPolicy.version.desc())
        )
    ]


@router.post("/policies")
def new_policy(data: PolicyRequest, db: DB, actor: User):
    authorize(actor, admin=True)
    current = db.scalar(
        select(ScoringPolicy)
        .where(ScoringPolicy.agent_type == data.agent_type)
        .order_by(ScoringPolicy.version.desc())
        .with_for_update()
    )
    row = ScoringPolicy(
        agent_type=data.agent_type,
        version=(current.version if current else 0) + 1,
        criteria=[c.model_dump() for c in data.criteria],
        created_by=actor.id,
    )
    db.add(row)
    db.flush()
    audit(db, actor.id, "policy.version_created", row)
    return serialize(row)


@router.post("/candidates/{candidate_id}/rescore")
def rescore(candidate_id: str, db: DB, actor: User):
    candidate = get_candidate(db, candidate_id, True)
    authorize(actor, candidate.domain_mode)
    result = calculate(db, candidate)
    audit(
        db,
        actor.id,
        "candidate.rescored",
        candidate,
        {"score_id": result.id, "rubric_version": result.rubric_version},
    )
    return serialize(result)


@router.get("/audit")
def audit_log(db: DB, actor: User, entity_id: str | None = None):
    statement = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(250)
    if entity_id:
        statement = statement.where(AuditEvent.entity_id == entity_id)
    return [serialize(a) for a in db.scalars(statement)]
