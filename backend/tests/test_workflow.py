from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.auth import Actor, current_actor
from app.database import session_factory
from app.models import Candidate, Followup, Handoff, Message, OutboxEvent, SearchJob
from app.services.business import trigger_followup
from tests.conftest import post


def approve_and_draft(client, candidate_id):
    assert post(client, f"/api/candidates/{candidate_id}/review", {"action": "APPROACH"}).status_code == 200
    response = post(client, f"/api/candidates/{candidate_id}/drafts", {"channel": "EMAIL"})
    assert response.status_code == 200, response.text
    return response.json()


def send(client, draft):
    assert (
        post(client, f"/api/drafts/{draft['id']}/approve", {"expected_version": draft["version"]}).status_code
        == 200
    )
    result = post(client, f"/api/drafts/{draft['id']}/send", {"expected_version": draft["version"]})
    assert result.status_code == 200, result.text
    return result.json()


def test_end_to_end_review_edit_send_reply_handoff(client, candidate_id, db):
    candidate = client.get(f"/api/candidates/{candidate_id}").json()
    assert candidate["evidence"][0]["source_url"].startswith("https://")
    assert candidate["score"]["total"] == 90
    assert post(client, f"/api/candidates/{candidate_id}/drafts", {"channel": "EMAIL"}).status_code == 409
    draft = approve_and_draft(client, candidate_id)
    assert "sourcing" in draft["body"]
    assert post(client, f"/api/drafts/{draft['id']}/approve", {"expected_version": 1}).status_code == 200
    edited = client.patch(
        f"/api/drafts/{draft['id']}",
        json={
            "subject": draft["subject"],
            "body": draft["body"] + "\nWe look forward to learning about your harvest.",
            "expected_version": 1,
        },
    ).json()
    assert edited["version"] == 2 and edited["approval_status"] == "PENDING"
    assert post(client, f"/api/drafts/{draft['id']}/send", {"expected_version": 1}).status_code == 409
    message = send(client, edited)
    duplicate = post(client, f"/api/drafts/{draft['id']}/send", {"expected_version": 2}).json()
    assert message["id"] == duplicate["id"] and message["simulated"]
    reply = post(
        client,
        f"/api/candidates/{candidate_id}/replies",
        {"body": "We are interested; our offer is attached."},
        "same-reply",
    )
    assert reply.json()["classification"]["intent"] == "OFFER_RECEIVED"
    assert (
        post(
            client,
            f"/api/candidates/{candidate_id}/replies",
            {"body": "We are interested; our offer is attached."},
            "same-reply",
        ).json()["id"]
        == reply.json()["id"]
    )
    first = post(client, f"/api/candidates/{candidate_id}/handoff").json()
    second = post(client, f"/api/candidates/{candidate_id}/handoff").json()
    assert first["id"] == second["id"]
    assert db.scalar(select(func.count(Message.id))) == 2
    assert db.scalar(select(func.count(Handoff.id))) == 1


def test_do_not_contact_blocks_previously_approved_send(client, candidate_id):
    draft = approve_and_draft(client, candidate_id)
    post(client, f"/api/drafts/{draft['id']}/approve", {"expected_version": 1})
    assert (
        post(
            client, f"/api/candidates/{candidate_id}/do-not-contact", {"notes": "Requested no contact"}
        ).status_code
        == 200
    )
    assert post(client, f"/api/drafts/{draft['id']}/send", {"expected_version": 1}).status_code == 409


def test_archive_keeps_business_records(client, candidate_id, db):
    assert post(client, f"/api/candidates/{candidate_id}/review", {"action": "ARCHIVE"}).status_code == 200
    assert client.delete(f"/api/candidates/{candidate_id}").status_code == 405
    assert client.get(f"/api/candidates/{candidate_id}").json()["archived_at"]
    assert db.get(Candidate, candidate_id)
    assert not client.get("/api/candidates").json()
    assert client.get("/api/dashboard").json()["high_priority_candidates"] == 0


def test_reply_cancels_followup(client, candidate_id):
    draft = approve_and_draft(client, candidate_id)
    send(client, draft)
    followup = post(
        client,
        f"/api/candidates/{candidate_id}/followups",
        {"due_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
        "same-followup",
    ).json()
    post(client, f"/api/candidates/{candidate_id}/replies", {"body": "Yes, interested"})
    with session_factory()() as db:
        row = db.get(Followup, followup["id"])
        assert row.status == "CANCELLED_REPLY"
        row.due_at = datetime.now(UTC) - timedelta(seconds=1)
        trigger_followup(db, row.id)
        assert row.draft_id is None


def test_due_followup_creates_only_unapproved_draft(client, candidate_id):
    draft = approve_and_draft(client, candidate_id)
    send(client, draft)
    followup = post(
        client,
        f"/api/candidates/{candidate_id}/followups",
        {"due_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
    ).json()
    with session_factory()() as db:
        row = db.get(Followup, followup["id"])
        row.due_at = datetime.now(UTC) - timedelta(seconds=1)
        db.flush()
        trigger_followup(db, row.id)
        first_id = row.draft_id
        trigger_followup(db, row.id)
        assert row.status == "DRAFT_READY" and row.draft_id == first_id
        assert db.scalar(select(func.count(Message.id))) == 1


def test_viewer_cannot_create_or_review(client, candidate_id):
    from app.main import app

    app.dependency_overrides[current_actor] = lambda: Actor("viewer", "Viewer", {"VIEWER"})
    assert client.get("/api/candidates").status_code == 200
    assert (
        post(client, "/api/jobs", {"agent_type": "SOURCING", "query": "Ethiopia producers"}).status_code
        == 403
    )
    assert post(client, f"/api/candidates/{candidate_id}/review", {"action": "APPROACH"}).status_code == 403


def test_transactional_job_creation_and_idempotency(client, db):
    body = {"agent_type": "LEAD", "query": "Coffee buyers Japan"}
    first = post(client, "/api/jobs", body, "repeated-key")
    second = post(client, "/api/jobs", body, "repeated-key")
    assert first.json()["id"] == second.json()["id"]
    assert db.scalar(select(func.count(SearchJob.id))) == 1
    assert db.scalar(select(func.count(OutboxEvent.id))) == 1
    assert post(client, "/api/jobs", {**body, "query": "different query"}, "repeated-key").status_code == 409


def test_document_extraction_and_human_review(client, candidate_id):
    content = b"supplier,origin,lot,price,currency\nFictional Farm,Ethiopia,Lot A,12,USD\n"
    response = client.post(
        f"/api/candidates/{candidate_id}/documents", files={"file": ("offer.csv", content, "text/csv")}
    )
    assert response.status_code == 200, response.text
    again = client.post(
        f"/api/candidates/{candidate_id}/documents", files={"file": ("offer.csv", content, "text/csv")}
    )
    assert again.json()["id"] == response.json()["id"]
    candidate = client.get(f"/api/candidates/{candidate_id}").json()
    offer = candidate["offers"][0]
    assert offer["extracted_data"]["origin"] == "Ethiopia"
    assert offer["review_status"] == "HUMAN_REVIEW_REQUIRED"
    assert (
        client.patch(f"/api/offers/{offer['id']}", json=offer["extracted_data"]).json()["review_status"]
        == "HUMAN_REVIEWED"
    )
    assert client.get(f"/api/documents/{response.json()['id']}/download").content == content


def test_instagram_never_uses_email_send(client, candidate_id):
    post(client, f"/api/candidates/{candidate_id}/review", {"action": "APPROACH"})
    draft = post(client, f"/api/candidates/{candidate_id}/drafts", {"channel": "INSTAGRAM"}).json()
    post(client, f"/api/drafts/{draft['id']}/approve", {"expected_version": 1})
    assert post(client, f"/api/drafts/{draft['id']}/send", {"expected_version": 1}).status_code == 409
    assert (
        post(client, f"/api/drafts/{draft['id']}/record-manual-send", {"expected_version": 1}).status_code
        == 200
    )


def test_early_followup_trigger_is_not_acknowledged(client, candidate_id):
    draft = approve_and_draft(client, candidate_id)
    send(client, draft)
    followup = post(
        client,
        f"/api/candidates/{candidate_id}/followups",
        {"due_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()},
    ).json()
    with session_factory()() as db:
        assert trigger_followup(db, followup["id"]) is False
        assert db.get(Followup, followup["id"]).status == "SCHEDULED"


def test_human_can_approve_after_additional_research(client, candidate_id):
    assert (
        post(client, f"/api/candidates/{candidate_id}/review", {"action": "RESEARCH_MORE"}).status_code == 200
    )
    assert post(client, f"/api/candidates/{candidate_id}/drafts", {"channel": "EMAIL"}).status_code == 409
    assert (
        post(
            client,
            f"/api/candidates/{candidate_id}/review",
            {"action": "APPROACH", "notes": "Human research completed"},
        ).status_code
        == 200
    )
    assert post(client, f"/api/candidates/{candidate_id}/drafts", {"channel": "EMAIL"}).status_code == 200


def test_incoming_reply_does_not_unarchive_candidate(client, candidate_id):
    draft = approve_and_draft(client, candidate_id)
    send(client, draft)
    post(client, f"/api/candidates/{candidate_id}/review", {"action": "ARCHIVE"})
    reply = post(client, f"/api/candidates/{candidate_id}/replies", {"body": "We are interested"})
    assert reply.status_code == 200
    assert client.get(f"/api/candidates/{candidate_id}").json()["current_status"] == "ARCHIVED"
