# Implementation plan

1. Inspect and record the empty workspace; build a standalone monorepo.
2. Establish PostgreSQL, FastAPI, React, migrations, fictional seeds and health checks.
3. Implement provenance, versioned deterministic scoring, reviews and audited transitions.
4. Implement separate LeadAgent and SourcingAgent configurations, validated Bedrock outputs and bounded tools.
5. Implement durable discovery checkpoints, transactional outbox, retries and queue idempotency.
6. Complete the local UI flow through approved mock outreach, replies, documents, follow-ups and handoff.
7. Add Cognito, SQS, S3, Scheduler and Secrets Manager adapters without requiring AWS for tests.
8. Prepare development and production Terraform, CI and operating documentation.
9. Run migrations, tests, builds and recovery scenarios; report actual verification and limitations.

No existing Qima application is touched. No remote commit/push, real messages or Terraform apply is authorized.

## Acceptance

The critical flow selects Sourcing, searches Ethiopia, reviews source evidence and deterministic scores, approves a candidate, creates and edits a draft, approves a simulated email, classifies a simulated reply and creates an idempotent handoff. Additional tests cover crash recovery, duplicate delivery, permissions, URL safety, approval invalidation and follow-up cancellation.

## Verification outcome

The local implementation and acceptance flow are complete and verified. AWS adapter implementation and Terraform validation are complete; account-backed verification and deployment await external configuration and explicit provisioning approval. See [BUILD_STATUS.md](BUILD_STATUS.md) for measured results and remaining prerequisites.
