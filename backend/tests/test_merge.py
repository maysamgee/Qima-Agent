from sqlalchemy import select

from app.database import session_factory
from app.integrations.demo import demo_profiles
from app.models import AuditEvent, Candidate, CandidateEvidence
from app.repositories import upsert_candidate
from app.scoring import calculate
from tests.conftest import post


def test_merge_keeps_original_record_and_requires_fresh_review(client, candidate_id):
    with session_factory()() as db:
        profile = demo_profiles("SOURCING", "Ethiopia")[0].model_copy(
            update={"instagram_handle": "separate_reference"}
        )
        source, _ = upsert_candidate(db, profile, "SOURCING", None)
        source_id = source.id
        calculate(db, source)
        db.commit()
    response = post(
        client,
        f"/api/candidates/{source_id}/review",
        {
            "action": "MERGE_DUPLICATE",
            "merge_target_id": candidate_id,
            "notes": "Confirmed same fictional producer",
        },
    )
    assert response.status_code == 200, response.text
    source = client.get(f"/api/candidates/{source_id}").json()
    target = client.get(f"/api/candidates/{candidate_id}").json()
    assert source["archived_at"] and source["merged_into_id"] == candidate_id
    assert target["reviews"][0]["action"] == "RESEARCH_MORE"
    assert post(client, f"/api/candidates/{candidate_id}/drafts", {"channel": "EMAIL"}).status_code == 409
    with session_factory()() as db:
        assert db.get(Candidate, source_id)
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "candidate.merge_received"))
        assert all(e.candidate_id == candidate_id for e in db.scalars(select(CandidateEvidence)))


def test_lead_query_targets_japan_not_yemeni_product_origin():
    rows = demo_profiles(
        "LEAD", query="Find potential buyers in Japan for high-quality Yemeni specialty coffee"
    )
    assert len(rows) == 1 and rows[0].country == "Japan"
