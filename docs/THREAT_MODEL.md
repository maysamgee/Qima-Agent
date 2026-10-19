# Threat model

| Threat | Boundary / control | Residual risk |
|---|---|---|
| Website prompt injection | Untrusted data wrapper, typed allowlisted tools, schema validation, server-owned approvals and score policy | A model may still misinterpret evidence; humans verify claims |
| SSRF/DNS rebinding | Exact approved HTTPS hosts; resolve all addresses; reject nonglobal IPs; pin connection; TLS hostname verification | Administrators must review allowed sources and network egress |
| Duplicate job/message | Outbox, advisory lock, durable checkpoints, unique business keys | Provider reads may repeat before a checkpoint commit |
| Unauthorized outreach | Local mock only; backend roles; candidate review; draft-version approval; suppression checks | A human can still copy text and act outside the platform |
| Stale follow-up | Reload database state and most recent reply; no auto-send | Real mailbox ingestion is not yet implemented |
| Forged JWT / client confusion | RS256 JWKS, issuer, exp/iat, token_use=access, client_id | Token theft via browser compromise; short expiry and CSP mitigate |
| XSS from research/replies | React text rendering, no HTML injection, static frontend CSP | Future rich-text features need a reviewed sanitizer |
| Malicious attachments | Size/type/signature checks; inert storage; attachment download; no active parser | Malware scanning must precede broader untrusted production intake |
| Secret leakage | Task roles/SSO, Secrets Manager, no secret values in Terraform, minimal structured logs | State and operations tooling still require scoped access |
| Business data loss | Archive-only APIs, immutable revisions, RDS backup/PITR, S3 versioning | Restore procedures must be rehearsed in the target AWS account |
| Resource exhaustion | Bounded model tokens, iteration/tool time limits, upload limits, per-process write limiter | Global rate limiting, per-user quotas and hard process cancellation remain production work |

Trust boundaries: browser → authenticated API; API/worker → PostgreSQL; worker → AWS transport; AI → typed backend services; external web/document text → untrusted evidence. Queue payloads never carry authority to approve or send.

Administrators can create policy versions; they cannot retroactively rewrite existing score records through the application. Database administrators remain a privileged trust boundary and need separate audit/backup controls.
