# Qima Coffee — Discovery & Outreach Agent Platform

A standalone, local-first workspace for two explicit objectives: **Find Buyers** (Lead Agent, sell coffee) and **Find Suppliers** (Sourcing Agent, buy coffee).

React + Vite + TypeScript, FastAPI, SQLAlchemy/Alembic, PostgreSQL, a separate discovery worker, and optional AWS adapters. PostgreSQL owns state and approvals; AI researches and drafts. No Step Functions.

**Default mode: FULL MOCK. All six demonstration organizations and addresses are fictional. No real emails or Instagram messages are sent.** No existing Qima, Base44, Lovable or Supabase application is involved.

## Start on Windows

Install Python 3.12+, Node.js 22.12+ (tested with 24), and Docker Desktop with Linux containers. Start Docker Desktop. Open PowerShell in this repository:

```powershell
Copy-Item .env.example .env # Only if you do not already have .env
.\scripts\bootstrap-local.ps1
.\scripts\run-local.ps1
```

If Python is not on PATH, pass its full path to bootstrap:

```powershell
.\scripts\bootstrap-local.ps1 -Python 'C:\path\to\python.exe'
```

Open **http://localhost:5173**, select **Enter local workspace**, then **Find Suppliers**. The API is http://localhost:8000 and Swagger is http://localhost:8000/docs.

The startup script preserves existing services if ports are occupied. Background process IDs and logs are in `.local/`. PostgreSQL data is retained in the Compose named volume. Do not remove that volume to restart services.

## Manual startup, one terminal per service

```powershell
Copy-Item .env.example .env # First run only
docker compose up -d --wait postgres
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e './backend[dev]'
Set-Location backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m app.seed
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

In a second terminal at the repository root:

```powershell
.\.venv\Scripts\python.exe -m worker.app.main
```

In a third terminal:

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run dev
```

macOS/Linux: `bash scripts/bootstrap-local.sh` then `bash scripts/run-local.sh`.

## Verify

```powershell
.\scripts\test.ps1
Set-Location frontend
npx.cmd playwright install chromium
npm.cmd run test:e2e # API, worker and frontend must be running
```

From the repository root:

```powershell
docker compose build api worker
.\.venv\Scripts\python.exe scripts/postgres-recovery.py
terraform fmt -check -recursive infra
terraform -chdir=infra/environments/dev init -backend=false
terraform -chdir=infra/environments/dev validate
terraform -chdir=infra/environments/prod init -backend=false
terraform -chdir=infra/environments/prod validate
```

`backend/requirements-tested.txt` records the tested dependency versions; `frontend/package-lock.json` and Terraform lock files pin their resolved dependencies. The repository-local `.tools/terraform.exe` used during this build is ignored and is not required if Terraform is installed normally.

## What works locally

- Explicit agent selection; fictional, country-filtered discovery; persistent progress and restart-safe checkpoints.
- Provenance, exact and probable deduplication, manual merge, separate fit/confidence, immutable rubric versions.
- Human review, edited draft history, per-version approval, idempotent simulated email and manually recorded Instagram.
- Simulated reply classification and corrections, follow-up drafts, document storage, offer review, commercial handoff and audit history.
- Backend role enforcement, production configuration guards, URL and DNS safety, bounded research tools, upload limits and structured logs.

## AWS modes and boundaries

Set `AI_PROVIDER=bedrock` with `AWS_REGION` and an enabled `BEDROCK_MODEL_ID` or `BEDROCK_INFERENCE_PROFILE_ARN`. Use an AWS profile/SSO locally and ECS task roles in AWS. Never add AWS keys to `.env` or source control.

Add development SQS and S3 only after the local workflow works. Development Terraform creates the small shared resource set; production Terraform also describes Cognito, CloudFront, networking, ALB, ECS and private RDS. **No Terraform apply is included in local startup or CI. Any apply requires explicit human approval.**

Live AWS calls, a real discovery vendor, production deployment and external OAuth cannot be verified without your account configuration. Gmail/Meta sending remains deliberately unimplemented and disabled.

## Documentation

Start with [local development](docs/LOCAL_DEVELOPMENT.md), [demo script](docs/DEMO_SCRIPT.md), [architecture](docs/ARCHITECTURE.md), and [build status](docs/BUILD_STATUS.md). See [AWS deployment](docs/AWS_DEPLOYMENT.md), [Terraform](docs/TERRAFORM.md), [security](docs/SECURITY.md), [recovery](docs/RESILIENCE_AND_RECOVERY.md), and [known limitations](docs/KNOWN_LIMITATIONS.md) before production use.
