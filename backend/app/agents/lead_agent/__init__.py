from app.agents.shared import GUARDRAILS
from app.schemas import LeadOutput


class LeadAgent:
    agent_type = "LEAD"
    objective = "Find companies that may buy coffee from Qima. Qima is SELLING coffee."
    system_prompt = GUARDRAILS + objective
    search_policy = (
        "Search specialty portfolios, origin launches, importing, buying, trade shows and sourcing contacts."
    )
    target_entity_types = [
        "specialty roaster",
        "importer",
        "green coffee trader",
        "roasting group",
        "distributor",
        "institutional buyer",
    ]
    evidence_priorities = ["buyer_activity", "product", "coffee_listing", "trade_show", "contact"]
    output_schema = LeadOutput
    scoring_policy = "lead"
    outreach_prompt = "Offer to explore buying coffee from Qima. Ask about buying priorities. Do not claim unverified stock, certifications or quality scores."
    prompt_version = "lead-v1"
