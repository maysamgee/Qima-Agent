# ADR 0002: Typed providers and simulated outreach

Status: accepted.

Discovery, AI, file storage and transport use replaceable adapters. Mock data is explicitly fictional. A real approved search endpoint must be configured and validated before production; no Google-result scraping or unofficial Instagram automation is implemented.

V1 implements only mock email and manual Instagram records. Configuration rejects real-send flags. This permits complete workflow testing without contacting anyone and avoids claiming exactly-once delivery from providers without a reviewed reconciliation mechanism.

Use Bedrock Converse with JSON-schema instructions and Pydantic validation; no hard-coded model and no unsupported AgentCore API guesses. Invalid/truncated output fails visibly and can be retried from durable checkpoints.
