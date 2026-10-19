import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Candidate, CandidateEvidence, ScoringPolicy, ScoringResult


def seed_policies(db: Session):
    for file in (Path(__file__).parent / "lead.json", Path(__file__).parent / "sourcing.json"):
        data = json.loads(file.read_text())
        if not db.scalar(
            select(ScoringPolicy).where(
                ScoringPolicy.agent_type == data["agent_type"], ScoringPolicy.version == 1
            )
        ):
            db.add(ScoringPolicy(**data))
    db.flush()


def score_band(total: int) -> str:
    for minimum, band in [
        (80, "Priority Candidate"),
        (65, "Strong Candidate"),
        (50, "Additional Research Required"),
        (35, "Weak Candidate"),
        (0, "Not Relevant"),
    ]:
        if total >= minimum:
            return band
    raise ValueError("Negative score")


def evidence_confidence(evidence: list[CandidateEvidence], missing: list[str]) -> tuple[str, str]:
    credible = [e for e in evidence if e.confidence >= 0.6 and e.verification_status != "CONFLICTING"]
    domains = {e.source_domain for e in credible}
    if not credible:
        return "INSUFFICIENT", "No sufficiently supported evidence; research is required."
    if any(e.verification_status == "CONFLICTING" for e in evidence):
        return "LOW", "Sources conflict; identity or claims require human resolution."
    verified = any(e.verification_status in {"VERIFIED", "CORROBORATED"} for e in credible)
    fresh = any(e.freshness_status == "FRESH" for e in credible)
    contact = any(e.category == "contact" for e in credible)
    if len(domains) >= 3 and verified and fresh and contact and not missing:
        return "HIGH", "At least three source domains, corroboration, recent evidence and a contact source."
    if len(domains) >= 2 and verified and fresh and len(missing) <= 1:
        return "MEDIUM", "At least two source domains and recent corroboration; some verification remains."
    return (
        "LOW",
        "Limited independent, verified or fresh sources, or unavailable evidence. Missing sources are not negative business signals.",
    )


def freshness(published_at: datetime | None) -> str:
    if not published_at:
        return "UNKNOWN"
    age = (datetime.now(UTC) - published_at.replace(tzinfo=UTC)).days
    return "FRESH" if 0 <= age <= 180 else "STALE" if age > 180 else "UNKNOWN"


def calculate(db: Session, candidate: Candidate) -> ScoringResult:
    policy = db.scalar(
        select(ScoringPolicy)
        .where(ScoringPolicy.agent_type == candidate.domain_mode)
        .order_by(ScoringPolicy.version.desc())
    )
    if policy is None:
        raise ValueError("Scoring policy not seeded")
    evidence = list(
        db.scalars(select(CandidateEvidence).where(CandidateEvidence.candidate_id == candidate.id))
    )
    evidence_hash = hashlib.sha256(
        json.dumps(
            [(e.id, e.raw_metadata, e.verification_status) for e in sorted(evidence, key=lambda e: e.id)]
        ).encode()
    ).hexdigest()
    existing = db.scalar(
        select(ScoringResult).where(
            ScoringResult.candidate_id == candidate.id,
            ScoringResult.policy_id == policy.id,
            ScoringResult.evidence_hash == evidence_hash,
        )
    )
    if existing:
        return existing
    supported: dict[str, list[str]] = {}
    for e in evidence:
        if e.verification_status == "CONFLICTING":
            continue
        for signal in e.raw_metadata.get("signals", []):
            supported.setdefault(signal, []).append(e.id)
    breakdown = []
    for criterion in policy.criteria:
        hits = [s for s in criterion["signals"] if s in supported]
        points = round(criterion["weight"] * len(hits) / len(criterion["signals"]))
        breakdown.append(
            {
                **criterion,
                "points": points,
                "evidence_ids": sorted({eid for h in hits for eid in supported[h]}),
                "explanation": "Supported: " + ", ".join(hits)
                if hits
                else "Evidence missing; no points established, not a negative finding.",
            }
        )
    total = sum(c["points"] for c in breakdown)
    confidence, explanation = evidence_confidence(evidence, candidate.missing_evidence)
    result = ScoringResult(
        candidate_id=candidate.id,
        policy_id=policy.id,
        rubric_version=policy.version,
        evidence_hash=evidence_hash,
        total=total,
        band=score_band(total),
        evidence_confidence=confidence,
        confidence_explanation=explanation,
        breakdown=breakdown,
    )
    db.add(result)
    db.flush()
    return result
