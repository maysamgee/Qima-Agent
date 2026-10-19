from app.agents.shared import GUARDRAILS
from app.schemas import SourcingOutput


class SourcingAgent:
    agent_type = "SOURCING"
    objective = "Find producers and sourcing partners from whom Qima may BUY coffee."
    system_prompt = GUARDRAILS + objective
    search_policy = "Search origin, varieties, processing, harvest, current crop, lots, samples, market mentions and producer networks. Producer-direct candidates are eligible; exporting is not required."
    target_entity_types = [
        "producer",
        "producer group",
        "exporter",
        "cooperative",
        "washing station",
        "mill",
        "origin supplier",
        "sourcing partner",
    ]
    evidence_priorities = [
        "production",
        "supplier_activity",
        "coffee_listing",
        "network_relationship",
        "contact",
    ]
    output_schema = SourcingOutput
    scoring_policy = "sourcing"
    outreach_prompt = "Explore sourcing from the recipient. Respect producer expertise; ask for current lots, samples and an offer or price list. Never presume export capability."
    prompt_version = "sourcing-v1"
