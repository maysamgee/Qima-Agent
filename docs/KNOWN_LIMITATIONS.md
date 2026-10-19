# Known limitations and production prerequisites

The local mock application is executable and tested. “Production-oriented” describes its architecture and controls; it is not a claim that an unconfigured AWS deployment is production-ready.

## Credential-dependent verification

Live Bedrock model access, approved real web discovery, SQS/DLQ, S3, Scheduler, Cognito hosted sign-in, Secrets Manager and ECS deployment were not exercised against an AWS account. Bedrock/SQS/S3/Scheduler calls have mocked SDK tests; Cognito cryptographic validation has local tests. Terraform validates against the installed AWS provider, but no credentialed plan/apply was run.

Gmail OAuth and Meta messaging are intentional V1 stubs. Real-email and real-Instagram flags are rejected. No real external messages were sent. Account-specific AgentCore browsing/search was not activated without verified capability.

## Research quality

Mock discovery contains six fictional organizations and country matching, not internet search. Non-demo discovery requires the documented approved API contract and reviewed source permissions. Dedicated trade-show, listing and enrichment adapters are unconfigured interfaces; existing evidence can still come from the shared search provider. Source-analysis checkpoints honestly inventory collected evidence and label unavailable sources.

Evidence confidence is an explicit heuristic. Domain count does not prove ownership independence. Signal extraction can be mistaken, and an eligible producer is not automatically a verified business contact. Human identity/commercial verification remains essential.

The web fetcher supports approved HTTPS HTML/text sources and fails closed on redirects, unsupported encodings and uncertain robots access. It is intentionally conservative and is not a general browser. Hard cancellation of a blocked SDK/DNS call requires process isolation; thread timeout discards results but cannot terminate a running thread. Network operations also have their own timeouts.

## Operations and scale

- The local queue is PostgreSQL polling; only AWS mode exercises transport visibility and DLQ mechanics.
- Unit tests use isolated SQLite databases; a separate local PostgreSQL subprocess recovery test and the full browser flow validate PostgreSQL behavior. High-load concurrency/failover testing is still required for the target infrastructure.
- Retries are bounded; SQS controls transport delay and local polling retries on later ticks. Sophisticated retry backoff, global per-user quotas and provider circuit breakers are future enhancements.
- The application write limiter is per process. Configure centralized/edge rate limits before public traffic. AWS alarms need SNS action ARNs and operations ownership; no live pager or target-account SLO dashboards were configured.
- The API exposes a bounded first page for candidate/job/audit lists, not full cursor pagination or enterprise search.
- TXT/CSV offer extraction supports structured fields (mock mode reads the first CSV row). PDF/DOCX/XLSX files are inert metadata/storage only; no OCR or macro execution. Add malware scanning/quarantine before broader production attachment ingestion.
- Local file writes/S3 puts and database transactions are not distributed transactions. Failed database writes may leave unreferenced objects for an operator-reviewed reconciliation process.
- Cognito sign-in uses sessionStorage access tokens and no automatic refresh; expired sessions require signing in again. A BFF/HttpOnly-cookie design may be appropriate for stricter deployments.
- Real mailbox/webhook ingestion is not implemented; development replies are simulated. There is no real-send reconciliation path because external sending is disabled.
- Frontend role-aware hiding is limited; backend authorization is authoritative and rejects unauthorized mutations. Some review/admin controls remain visible to read-only users.
- GitHub Actions files are prepared, but no remote repository, environment protection, OIDC trust, branch protection or deployment role was created.

Database secrets, model entitlements, approved provider credentials, regional certificates, DNS, scoped database grants and organizational security/retention policies must be supplied before production activation. Keep ECS desired counts at zero until these prerequisites and migrations are satisfied. No expensive AWS infrastructure was provisioned.
