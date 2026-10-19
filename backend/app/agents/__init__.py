from app.agents.lead_agent import LeadAgent
from app.agents.sourcing_agent import SourcingAgent
from app.schemas import Mode


def get_agent(mode: str):
    return {Mode.LEAD: LeadAgent, Mode.SOURCING: SourcingAgent}[Mode(mode)]()
