# BUILD STATUS

Verified locally on 21 September 2026. **The standalone FULL MOCK application is running and its critical business workflow passes. AWS deployment and live provider operation remain unverified without account configuration.**

**Later AWS connection update:** the `qima-deploy` profile is now authenticated through SSO. Read-only account checks passed, but the assigned `NetworkAdministrator` role was denied access to ECS, RDS, ECR, Cognito, S3, ACM, Bedrock and IAM inspection operations. No deployment occurred. See [AWS access request](AWS_ACCESS_REQUEST.md).

Repository: `C:\Users\Hp\Desktop\QIMA AGENT\qima-agents`. No existing Qima application was changed. No real email or Instagram message was sent, no Terraform apply was run, and no remote repository was created, pushed or merged.

## Completed

- React/Vite/TypeScript interface covering agent selection, discovery progress, candidates, evidence, scoring, review, draft editing/approval, conversations, documents/offers, follow-ups, handoff, audit, rubric versions and integration health.
- FastAPI API, separate worker, PostgreSQL 16 through Docker Compose, 27 model tables, applied Alembic migration and six fictional demonstration organizations.
- Explicit LeadAgent and SourcingAgent with separate objectives, prompts, search policies, entity targets, evidence priorities, schemas and 100-point rubrics.
- Deterministic versioned scores; separate evidence confidence; provenance; exact/probable deduplication; audited manual merge; archive and do-not-contact controls.
- Durable job checkpoints, transactional outbox, bounded attempts, duplicate-delivery protection, local polling and SQS transport adapter.
- Human candidate review, draft revisions, approval invalidation after editing, idempotent simulated email, manual Instagram records, simulated replies and human classification correction.
- Local/S3 document storage, structured TXT/CSV offer extraction, metadata-only PDF/Office handling, human offer review, safe follow-up drafts and idempotent commercial handoff.
- Bedrock, SQS, S3, Scheduler, Secrets Manager and Cognito adapters; development/production infrastructure; CI and manually dispatched OIDC deployment workflow; setup scripts and operating documentation.

## Partially completed

- AWS integration code and Terraform configurations are implemented and locally checked; actual AWS service behavior, account permissions, quotas and deployment are not verified.
- Real search uses a configurable approved HTTPS API contract. Dedicated trade-show, listing, enrichment and Meta evidence services remain unconfigured interfaces and report unavailable status.
- Production hardening needs target-environment load/failover tests, centralized rate limiting, attachment quarantine/scanning, alert destinations and organizational security review.
- The GitHub workflow files exist locally; remote repository settings, protected environments, branch protection and OIDC trust require account administration.

## Blocked by missing credentials/access

The AWS SSO connection is established. Supply an approved deployment-capable role and confirm the hosting region; an enabled Bedrock model ID or inference-profile ARN; scoped resource permissions; and, after approved provisioning, SQS queue URLs, S3 bucket and Scheduler role/group. Real discovery needs an approved vendor endpoint/key and reviewed source allowlist.

Production additionally needs Cognito configuration/users/groups, regional ACM certificate and DNS, application database grants and Secrets Manager values, reviewed ECR artifacts, GitHub environment/OIDC configuration, and alarm destinations. Gmail OAuth and Meta account integration are intentionally inactive V1 stubs; activating real messaging requires separate implementation and explicit approval.

## Architecture implemented

React calls FastAPI. PostgreSQL owns candidates, evidence, score history, approvals, conversations, follow-ups and workflow checkpoints. API transactions create outbox events; the worker processes identifiers through local polling or SQS and resumes committed steps. Shared bounded tools and Bedrock/mock model services support two explicit business agents. Local storage or S3 holds documents. Scheduler triggers a database-state recheck before creating a follow-up draft. Humans authorize outreach and handoff. There are no Step Functions or autonomous agent-to-agent conversations.

See [architecture and diagrams](ARCHITECTURE.md), [agent design](AGENT_DESIGN.md) and [scoring rules](SCORING_RUBRICS.md).

## Local run instructions

The services were left running for review at [frontend](http://localhost:5173), [API](http://localhost:8000) and [API documentation](http://localhost:8000/docs). Choose **Enter local workspace**, then **Find Suppliers** or **Find Buyers**. The visible mode is FULL MOCK.

For a fresh setup with Python 3.12+, Node 22.12+ and Docker Desktop running:

```powershell
Set-Location 'C:\Users\Hp\Desktop\QIMA AGENT\qima-agents'
Copy-Item .env.example .env # First setup only; preserve an existing .env
.\scripts\bootstrap-local.ps1
.\scripts\run-local.ps1
```

If Python is not on PATH, pass `-Python 'C:\path\to\python.exe'` to bootstrap. The current workspace already has an installed `.venv`, frontend dependencies and an initialized database. The startup script refuses occupied ports and records its background processes/logs in `.local/`. Do not rerun it while these services are already running. See [local development](LOCAL_DEVELOPMENT.md) for individual service commands and [demo script](DEMO_SCRIPT.md) for a guided walkthrough.

## AWS development configuration

Keep the local API, worker and PostgreSQL. After reviewing and approving the small development resource plan, set:

```dotenv
AWS_PROFILE=qima-dev
AWS_REGION=<approved-region>
AI_PROVIDER=bedrock
QUEUE_PROVIDER=sqs
DISCOVERY_QUEUE_URL=<development-queue-url>
DISCOVERY_DLQ_URL=<development-dlq-url>
STORAGE_PROVIDER=s3
EVIDENCE_BUCKET=<development-bucket>
SCHEDULER_ROLE_ARN=<approved-scheduler-role>
SCHEDULER_GROUP=<development-scheduler-group>
EMAIL_PROVIDER=mock
INSTAGRAM_PROVIDER=manual
REAL_EMAIL_ENABLED=false
REAL_INSTAGRAM_SEND_ENABLED=false
```

Use SSO/temporary profile credentials locally and task roles in ECS. Keep mock search for an explicitly labelled hybrid development test, or configure the approved search API. See [AWS deployment](AWS_DEPLOYMENT.md) and [environment variables](ENVIRONMENT_VARIABLES.md).

## Terraform plan instructions

All three configurations passed provider-schema validation. No credentialed plan or apply was executed. With an approved profile and an existing approved state bucket:

```powershell
$env:AWS_PROFILE = 'qima-dev'
Set-Location infra\environments\dev
Copy-Item terraform.tfvars.example terraform.tfvars
Copy-Item backend.hcl.example backend.hcl
# Edit region, owner, resource and state-bucket settings.
terraform init -reconfigure -backend-config=backend.hcl
terraform plan -out=dev.tfplan
terraform show dev.tfplan
```

Stop for explicit human approval before apply. If a state bucket does not exist, review the bootstrap plan first. Do not commit state, plans, actual backend configuration or secret values. Production service desired counts default to zero pending images, database credentials and migrations. See [Terraform operations](TERRAFORM.md).

## Bedrock model configuration

Set `AI_PROVIDER=bedrock`, `AWS_REGION` and either `BEDROCK_MODEL_ID` or `BEDROCK_INFERENCE_PROFILE_ARN` to an identifier enabled in the actual account. No model ID is hard-coded. Temperature, output tokens, tool iterations, per-tool timeout and total job timeout are configurable. The service uses boto3 Converse and validates structured outputs with Pydantic. Run `scripts/bedrock-smoke.py` manually only after model access and billable inference are authorized.

## Mock versus real integrations

| Integration | Verified locally | Live status |
| --- | --- | --- |
| PostgreSQL/API/worker/UI | Real local processes and container database | Running |
| AI and discovery | Deterministic mock model; six fictional organizations | Bedrock/API search adapters require configuration |
| Email | Simulated persisted messages | Gmail stub; real sending disabled |
| Instagram | Draft/copy/manual-record workflow | No automated sending or unofficial scraping |
| Documents | Local file persistence; S3 SDK tests | Live bucket not configured |
| Queue/follow-up transport | Durable local polling; SQS/Scheduler SDK tests | Live queues/schedules not configured |
| Authentication | Visible local user; cryptographic JWT tests | Cognito hosted sign-in not exercised |
| Infrastructure/CI | Terraform validation and local checks | No AWS deployment or remote workflow execution |

## Tests executed and results

| Check | Result |
| --- | --- |
| Backend/worker pytest suite | **67 passed**; two upstream deprecation warnings |
| Final archive/current-score dashboard regression | **1 passed** after the dashboard adjustment |
| Ruff and mypy | Passed; mypy checked 34 source files |
| Frontend Vitest/React Testing Library | **4 passed** |
| ESLint, TypeScript and Vite production build | Passed |
| Playwright sourcing workflow | **1 passed**, final run 4.7 seconds; all 13 requested business steps |
| PostgreSQL migrations and seed | Passed against Docker PostgreSQL 16 |
| Separate-process PostgreSQL recovery | Passed; details below |
| Documented Windows startup script | Passed; frontend HTTP 200 and API readiness ready |
| API and worker Docker image builds | Both passed with final backend sources |
| Container runtime smoke checks | API readiness and worker tick passed against PostgreSQL |
| Terraform format and validation | Passed: bootstrap, dev and prod; Terraform 1.12.2, AWS provider 6.65.0 |
| Dependency audits | pip-audit and npm audit reported no known vulnerabilities at verification time |
| Interactive browser review | Dashboard, progress, evidence/profile and mobile layout inspected |

The repeat E2E run exposed a test timing race with previously sent drafts. The test now waits for the newly created draft and reply to appear; the rerun passed without clearing business history. Live AWS inference, transport, sign-in, deployment and production-scale tests were not run.

## Security controls implemented

Backend RBAC and Cognito claim/signature checks; production rejection of local auth and mock discovery/model settings; version-specific human approvals; duplicate/archive/do-not-contact enforcement; validated model outputs and bounded allowlisted tools; prompt-injection guardrails; approved HTTPS source policy, robots checks, DNS/public-IP checks and pinned TLS fetches; response/upload/type limits; timeouts and per-process rate limiting; CORS and security headers; private attachment downloads; immutable local writes; structured allowlisted logs and audit history.

Infrastructure describes private RDS, verified database TLS, non-root containers, scoped roles, encrypted/versioned private S3, encrypted queues, restricted security groups, retained backups, protected secret containers and OIDC deployment. These infrastructure controls are configured in code, not asserted to be deployed. See [security](SECURITY.md) and [threat model](THREAT_MODEL.md).

## Failure recovery test results

The PostgreSQL recovery script migrated a unique local schema, committed the deduplication checkpoint, exited the first worker process, then resumed and delivered the same job again. Completed steps were not repeated. The final job was PARTIAL because explicitly unavailable evidence sources are allowed. It retained **one candidate, three evidence records and one score**.

The retained verification schema is `qima_recovery_a9266ffb6b8143c89a7bd4cc20a19903`; job ID is `0e0b4ca5-5304-4c81-bace-4f84e6b5db5f`. No test schema was dropped. Unit tests also cover outbox failure/retry, queue duplicates, bounded permanent failure, edited-approval invalidation, stale follow-up cancellation and early follow-up delivery. See [resilience and recovery](RESILIENCE_AND_RECOVERY.md).

## Known limitations

Live AWS operation is unverified. Confidence is a documented heuristic, not calibrated certainty. Unconfigured evidence providers remain unavailable. PDF/Office files are metadata-only; CSV mock extraction reads the first row. Thread timeouts cannot forcibly terminate blocked calls. High-load behavior, centralized quotas, malware quarantine, full pagination, automatic Cognito refresh, real mailbox ingestion and complete frontend role-based control hiding remain future work. Local/S3 object writes and database transactions can leave unreferenced objects after a failure. See the full [known limitations](KNOWN_LIMITATIONS.md) before production activation.

## Next recommended step

Review the running local mock workflow using the demo script. Then supply an approved development AWS profile, region and enabled model/profile ID so the small development Terraform plan can be reviewed and Bedrock/SQS/S3 verified. Obtain explicit approval before provisioning or billable live actions; retain mock email and manual Instagram throughout development.
