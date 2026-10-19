from unittest.mock import Mock

import pytest
from sqlalchemy import func, select

from app.auth import Actor
from app.config import get_settings
from app.database import session_factory
from app.integrations.queue import publish_outbox
from app.models import Candidate, CandidateEvidence, OutboxEvent, ScoringResult, SearchJob, SearchJobStep
from app.schemas import SearchRequest
from app.workflow.discovery import create_job, process_job


def new_job():
    with session_factory()() as db:
        row = create_job(
            db,
            SearchRequest(agent_type="SOURCING", query="Find Ethiopian producers", country="Ethiopia"),
            Actor("tester", "Test", {"ADMIN"}),
            "job-key",
        )
        db.commit()
        return row.id


def test_worker_restart_skips_durable_completed_steps(database):
    job_id = new_job()
    with pytest.raises(SystemExit):
        process_job(job_id, fail_after_step="deduplication")
    with session_factory()() as db:
        before = {s.name: s.retry_count for s in db.scalars(select(SearchJobStep))}
        assert db.get(SearchJob, job_id).status == "RUNNING"
        assert db.scalar(select(func.count(Candidate.id))) == 1
    assert process_job(job_id, "recovery-message")
    with session_factory()() as db:
        assert db.get(SearchJob, job_id).status == "PARTIAL"
        steps = {s.name: s for s in db.scalars(select(SearchJobStep))}
        assert steps["deduplication"].retry_count == before["deduplication"] == 1
        assert steps["scoring"].status == "COMPLETED"


def test_duplicate_sqs_delivery_has_no_duplicate_business_effects(database):
    job_id = new_job()
    assert process_job(job_id, "sqs-message-one")
    assert process_job(job_id, "sqs-message-one")
    assert process_job(job_id, "sqs-message-two")
    with session_factory()() as db:
        assert db.scalar(select(func.count(Candidate.id))) == 1
        assert db.scalar(select(func.count(CandidateEvidence.id))) == 3
        assert db.scalar(select(func.count(ScoringResult.id))) == 1


def test_outbox_retries_failed_publish_without_losing_job(database, monkeypatch):
    new_job()
    get_settings().queue_provider = "sqs"
    queue = Mock()
    queue.publish.side_effect = RuntimeError("simulated transport outage")
    publish_outbox(queue)
    with session_factory()() as db:
        event = db.scalar(select(OutboxEvent))
        assert event.published_at is None and event.attempts == 1
        assert db.scalar(select(func.count(SearchJob.id))) == 1
    queue.publish.side_effect = None
    publish_outbox(queue)
    publish_outbox(queue)
    with session_factory()() as db:
        event = db.scalar(select(OutboxEvent))
        assert event.published_at and event.attempts == 2
    assert queue.publish.call_count == 2


def test_rollback_does_not_leave_orphan_outbox(database):
    with session_factory()() as db:
        create_job(
            db,
            SearchRequest(agent_type="LEAD", query="Find Japan buyers"),
            Actor("tester", "Test", {"ADMIN"}),
            "rollback",
        )
        db.rollback()
    with session_factory()() as db:
        assert db.scalar(select(func.count(SearchJob.id))) == 0
        assert db.scalar(select(func.count(OutboxEvent.id))) == 0
