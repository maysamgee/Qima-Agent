# Agent design

`LeadAgent` and `SourcingAgent` are explicit configurations sharing one controlled runtime and model service. The UI's selected `agent_type` is required by the search schema and validated again when the backend constructs an agent. Text cannot silently switch the objective.

The Lead Agent researches specialty roasters, importers, traders, distributors and buyers. It prioritizes portfolio, origin listings and buying signals. Its outreach explores the recipient buying from Qima.

The Sourcing Agent researches producers, producer groups, exporters, cooperatives, washing stations, mills and origin partners. It prioritizes production, current lots, samples and market validation. Producer-direct opportunities are eligible; neither an exporter designation nor a website is required. Its outreach asks about sourcing, samples and offer lists.

## Research loop

1. Validate the selected agent and research plan.
2. Allow only typed web search, approved website fetch, Instagram evidence, trade show, coffee listing and contact-enrichment tool calls.
3. Hash calls to skip repeated arguments. Enforce a maximum call budget, timeout per tool and a job deadline.
4. Mark source failures unavailable and retain successful results.
5. Extract a Pydantic-validated profile. Reject evidence URLs not supplied by tools.
6. Persist factual summaries and source references, not full fetched pages.

Network operations have their own timeouts. A Python thread cannot forcibly cancel an already-started blocking call; timed-out tool results are discarded, and tools have no message-sending or business-mutation capability. See known limitations for hard process isolation.

Website content, replies and documents are wrapped as untrusted data. System prompts prohibit instruction-following from sources, invented credentials/claims, unauthorized tools, policy changes and approval. Only backend services can change workflow state, compute scores or record approved mock sends.

## Model adapters

`BedrockModelService` uses boto3 `bedrock-runtime.converse`; no model ID is hard-coded. Region, profile, model/inference-profile, temperature and token budget are configurable. Planning, evidence extraction, classification, outreach, replies and offers use structured schemas. Truncated or invalid JSON is rejected. Model/token usage is retained in audit metadata where returned by AWS.

The default mock model is deterministic and requires no network. No agent-to-agent conversations or separate scoring/email/research agents exist.

## Real search provider contract

`ApprovedAPIWebSearchProvider` POSTs `{query, country, agent_type}` to the deployment-configured HTTPS endpoint using a bearer API key. The response must validate as `ToolResult`, including availability, provider, fictional=false, and at most 50 result objects. Objects must contain `source_url` and short factual material; evidence URLs must occur in these results. Vendor terms, robots policy, source quality and rate limits require operator review.

Trade-show, coffee-listing and enrichment provider interfaces report UNAVAILABLE until an approved adapter is supplied. Instagram is manual/approved evidence only. AgentCore was not activated: no selected AWS account or region capability was provided, so no unverified SDK calls were invented.
