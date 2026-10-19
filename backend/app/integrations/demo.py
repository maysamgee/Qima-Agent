from datetime import UTC, datetime
from typing import Any, cast

from pydantic import HttpUrl

from app.schemas import CandidateProfile, EvidenceInput

DEMO = [
    (
        "SOURCING",
        "Dawn Ridge Producer Collective",
        "Ethiopia",
        "producer",
        "dawn-ridge",
        "Washed and natural heirloom coffee from a fictional Sidama producer group.",
        False,
    ),
    (
        "SOURCING",
        "Cloud Valley Exports",
        "Colombia",
        "exporter",
        "cloud-valley",
        "Fictional Huila lots, washed Caturra and experimental processing.",
        True,
    ),
    (
        "SOURCING",
        "High Terrace Growers",
        "Yemen",
        "producer group",
        "high-terrace",
        "Fictional highland producer group with naturally processed coffee.",
        True,
    ),
    (
        "LEAD",
        "Kumo Atelier Coffee",
        "Japan",
        "specialty roaster",
        "kumo-atelier",
        "Fictional specialty roaster exploring distinctive origin coffees.",
        True,
    ),
    (
        "LEAD",
        "Lantern Green Imports",
        "United Kingdom",
        "importer",
        "lantern-green",
        "Fictional specialty green coffee importer serving independent roasters.",
        True,
    ),
    (
        "LEAD",
        "Copper Coast Distribution",
        "United States",
        "distributor",
        "copper-coast",
        "Fictional coffee distributor with a specialty portfolio.",
        True,
    ),
]


def demo_profiles(mode: str, country: str = "", query: str = "") -> list[CandidateProfile]:
    requested = country.strip().casefold()
    if not requested:
        requested = next(
            (c.casefold() for agent, _, c, *_ in DEMO if agent == mode and c.casefold() in query.casefold()),
            "",
        )
    aliases = {"uk": "united kingdom", "us": "united states", "usa": "united states"}
    requested = aliases.get(requested, requested)
    profiles = []
    for agent, name, nation, kind, slug, description, website in DEMO:
        if agent != mode or (requested and requested != nation.casefold()):
            continue
        signals = (
            [
                "supplier_type",
                "origin_fit",
                "specialty_product",
                "current_production",
                "market_validation",
                "business_activity",
                "commercial_contact",
            ]
            if mode == "SOURCING"
            else [
                "buyer_type",
                "specialty_portfolio",
                "origin_coffees",
                "active_buying",
                "business_activity",
                "external_coffee",
                "commercial_contact",
            ]
        )
        groups = [
            (
                "production" if mode == "SOURCING" else "buyer_activity",
                f"https://{slug}.example/coffee",
                signals[:4],
                description,
            ),
            (
                "coffee_listing",
                f"https://demo-coffee-market.example/{slug}",
                signals[4:6],
                f"Fictional coffee listing mentions {name}.",
            ),
            (
                "contact",
                f"https://demo-trade-directory.example/{slug}",
                signals[6:],
                "Fictional commercial email supplied for local simulation only.",
            ),
        ]
        evidence = [
            EvidenceInput(
                category=cast(Any, category),
                claim=claim,
                source_url=HttpUrl(url),
                source_title="FICTIONAL DEMO SOURCE",
                evidence_summary=claim,
                source_type="fictional_demo",
                published_at=datetime.now(UTC),
                confidence=0.8,
                verification_status="CORROBORATED",
                signals=sigs,
            )
            for category, url, sigs, claim in groups
        ]
        profiles.append(
            CandidateProfile(
                company_name=name,
                entity_type=kind,
                country=nation,
                website_url=HttpUrl(f"https://{slug}.example") if website else None,
                instagram_handle=slug.replace("-", "_"),
                company_bio="FICTIONAL DEMO — " + description,
                product_summary=description,
                email=f"hello@{slug}.example",
                evidence=evidence,
                missing_evidence=["Instagram: manual review required"],
                demo=True,
            )
        )
    return profiles
