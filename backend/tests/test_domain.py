from copy import deepcopy

import pytest
from sqlalchemy import func, select

from app.agents import get_agent
from app.integrations.demo import demo_profiles
from app.models import Candidate, CandidateEvidence, ScoringPolicy, ScoringResult
from app.repositories import normalize_domain, upsert_candidate
from app.scoring import calculate, evidence_confidence, score_band


@pytest.mark.parametrize("mode,phrase", [("LEAD", "SELLING"), ("SOURCING", "BUY")])
def test_explicit_agent_routing(mode, phrase):
    agent = get_agent(mode)
    assert phrase in agent.objective
    assert agent.agent_type == mode
    assert agent.output_schema is not get_agent("LEAD" if mode == "SOURCING" else "SOURCING").output_schema


@pytest.mark.parametrize(
    "score,expected",
    [
        (0, "Not Relevant"),
        (34, "Not Relevant"),
        (35, "Weak Candidate"),
        (49, "Weak Candidate"),
        (50, "Additional Research Required"),
        (64, "Additional Research Required"),
        (65, "Strong Candidate"),
        (79, "Strong Candidate"),
        (80, "Priority Candidate"),
        (100, "Priority Candidate"),
    ],
)
def test_score_thresholds(score, expected):
    assert score_band(score) == expected


def test_producer_direct_without_website_is_eligible_and_not_penalized(db):
    profile = demo_profiles("SOURCING", "Ethiopia")[0]
    assert profile.website_url is None
    candidate, _ = upsert_candidate(db, profile, "SOURCING", None)
    score = calculate(db, candidate)
    assert score.total == 90
    assert score.evidence_confidence == "MEDIUM"
    assert "producer" in get_agent("SOURCING").target_entity_types
    assert candidate.current_status == "WAITING_FOR_REVIEW"
    assert not candidate.archived_at


def test_new_and_missing_social_do_not_mean_inactive(db):
    profile = demo_profiles("LEAD", "Japan")[0]
    candidate, _ = upsert_candidate(db, profile, "LEAD", None)
    score = calculate(db, candidate)
    assert score.total == 90
    assert "inactiv" not in str(score.breakdown).lower()
    assert "Instagram" in candidate.missing_evidence[0]


def test_exact_dedup_preserves_evidence_and_score(db):
    profile = demo_profiles("LEAD", "Japan")[0]
    first, _ = upsert_candidate(db, profile, "LEAD", None)
    score = calculate(db, first)
    second, duplicate = upsert_candidate(db, profile, "LEAD", None)
    assert first.id == second.id and duplicate
    assert calculate(db, second).id == score.id
    assert db.scalar(select(func.count(Candidate.id))) == 1
    assert db.scalar(select(func.count(CandidateEvidence.id))) == 3
    assert db.scalar(select(func.count(ScoringResult.id))) == 1


def test_name_alone_does_not_merge_different_domains(db):
    profile = demo_profiles("LEAD", "Japan")[0]
    first, _ = upsert_candidate(db, profile, "LEAD", None)
    other = profile.model_copy(
        update={"website_url": "https://unrelated.example", "instagram_handle": "unrelated_company"}
    )
    second, duplicate = upsert_candidate(db, other, "LEAD", None)
    assert first.id != second.id and not duplicate
    assert second.risk_flags == [f"PROBABLE_DUPLICATE:{first.id}"]
    assert normalize_domain("https://WWW.COFFEE.EXAMPLE/path") == "coffee.example"


def test_versioned_policy_keeps_old_scores(db):
    candidate, _ = upsert_candidate(db, demo_profiles("SOURCING", "Ethiopia")[0], "SOURCING", None)
    old = calculate(db, candidate)
    policy = db.get(ScoringPolicy, old.policy_id)
    criteria = deepcopy(policy.criteria)
    criteria[0]["weight"] -= 5
    criteria[-2]["weight"] += 5
    db.add(ScoringPolicy(agent_type="SOURCING", version=2, criteria=criteria))
    db.flush()
    new = calculate(db, candidate)
    assert old.total == 90 and old.rubric_version == 1
    assert new.total == 85 and new.rubric_version == 2


def test_confidence_is_independent_of_fit(db):
    candidate, _ = upsert_candidate(db, demo_profiles("SOURCING", "Ethiopia")[0], "SOURCING", None)
    evidence = list(db.scalars(select(CandidateEvidence)))
    for row in evidence:
        row.source_domain = "single.example"
    score = calculate(db, candidate)
    assert score.total == 90 and score.evidence_confidence == "LOW"
    assert evidence_confidence([], ["Instagram unavailable"])[0] == "INSUFFICIENT"
