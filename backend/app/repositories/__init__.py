import hashlib
import re
from urllib.parse import urlsplit

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Candidate, CandidateAlias, CandidateEvidence, ContactPoint, JobCandidate
from app.schemas import CandidateProfile
from app.scoring import freshness


def normalize_name(name: str) -> str:
    return re.sub(r"[^\w]+", " ", name.casefold()).strip()


def normalize_domain(url: str | None) -> str | None:
    if not url:
        return None
    return (urlsplit(url).hostname or "").lower().removeprefix("www.").rstrip(".") or None


def upsert_candidate(db: Session, profile: CandidateProfile, mode: str, job_id: str | None):
    domain = normalize_domain(str(profile.website_url)) if profile.website_url else None
    handle = profile.instagram_handle.lstrip("@").casefold() if profile.instagram_handle else None
    name = normalize_name(profile.company_name)
    identity = f"{mode}:" + (
        f"domain:{domain}"
        if domain
        else f"instagram:{handle}"
        if handle
        else f"discovery:{job_id}:{name}:{profile.country.casefold()}"
    )
    alias = db.scalar(select(CandidateAlias).where(CandidateAlias.alias == identity))
    candidate = (
        db.get(Candidate, alias.candidate_id)
        if alias
        else db.scalar(select(Candidate).where(Candidate.identity_key == identity))
    )
    if not candidate and (domain or handle):
        conditions = []
        if domain:
            conditions.append(Candidate.normalized_domain == domain)
        if handle:
            conditions.append(Candidate.instagram_handle == handle)
        candidate = db.scalar(
            select(Candidate).where(
                Candidate.domain_mode == mode, Candidate.merged_into_id.is_(None), or_(*conditions)
            )
        )
    duplicate = bool(candidate)
    if not candidate:
        probable = db.scalar(
            select(Candidate).where(
                Candidate.domain_mode == mode,
                Candidate.normalized_name == name,
                Candidate.country == profile.country,
                Candidate.archived_at.is_(None),
            )
        )
        candidate = Candidate(
            domain_mode=mode,
            identity_key=identity,
            company_name=profile.company_name,
            normalized_name=name,
            entity_type=profile.entity_type,
            country=profile.country,
            origin_country=profile.country if mode == "SOURCING" else None,
            target_market=profile.country if mode == "LEAD" else None,
            website_url=str(profile.website_url) if profile.website_url else None,
            normalized_domain=domain,
            instagram_handle=handle,
            company_bio=profile.company_bio,
            product_summary=profile.product_summary,
            missing_evidence=profile.missing_evidence,
            risk_flags=[f"PROBABLE_DUPLICATE:{probable.id}"] if probable else [],
            demo=profile.demo,
        )
        db.add(candidate)
        db.flush()
    if job_id and not db.scalar(
        select(JobCandidate).where(JobCandidate.job_id == job_id, JobCandidate.candidate_id == candidate.id)
    ):
        db.add(JobCandidate(job_id=job_id, candidate_id=candidate.id))
    for evidence in profile.evidence:
        url = str(evidence.source_url)
        fingerprint = hashlib.sha256(
            f"{candidate.id}|{url}|{evidence.category}|{evidence.claim}".encode()
        ).hexdigest()
        if not db.scalar(select(CandidateEvidence).where(CandidateEvidence.fingerprint == fingerprint)):
            db.add(
                CandidateEvidence(
                    candidate_id=candidate.id,
                    fingerprint=fingerprint,
                    category=evidence.category,
                    claim=evidence.claim,
                    source_url=url,
                    source_domain=normalize_domain(url) or "unknown",
                    source_type=evidence.source_type,
                    source_title=evidence.source_title,
                    evidence_summary=evidence.evidence_summary,
                    published_at=evidence.published_at,
                    freshness_status=freshness(evidence.published_at),
                    confidence=evidence.confidence,
                    verification_status=evidence.verification_status,
                    collection_method="MOCK" if profile.demo else "approved_provider",
                    agent_type=mode,
                    job_id=job_id,
                    raw_metadata={"signals": evidence.signals, "fictional": profile.demo},
                )
            )
    if profile.email and not db.scalar(
        select(ContactPoint).where(
            ContactPoint.candidate_id == candidate.id,
            ContactPoint.kind == "EMAIL",
            ContactPoint.value == profile.email.lower(),
        )
    ):
        db.add(
            ContactPoint(
                candidate_id=candidate.id,
                kind="EMAIL",
                value=profile.email.lower(),
                verified=False,
                source_url=str(profile.website_url) if profile.website_url else None,
            )
        )
    db.flush()
    return candidate, duplicate
