# Local development

## Prerequisites

Use Python 3.12 or later, Node.js 22.12+ (24 tested), and Docker Desktop configured for Linux containers. Allow Docker to finish starting before running Compose. No AWS account is needed for full mock mode.

The exact PowerShell startup commands are in the root README. `bootstrap-local.ps1` installs dependencies, creates PostgreSQL, applies migrations and seeds demo data. `run-local.ps1` starts three background processes without visible helper windows. Review `.local/*-error.log` if a service does not start.

On the build machine Python was available at `C:\Users\Hp\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`; this is machine-specific, not a repository requirement. The installed `.venv\Scripts\python.exe` can now run the backend directly.

## Operating modes

| Mode | Configuration | External calls |
|---|---|---|
| FULL MOCK | Defaults in `.env.example` | None for discovery/AI/email |
| LOCAL + BEDROCK | `AI_PROVIDER=bedrock`; region and model/profile | Billable Bedrock inference; search can remain fictional |
| LOCAL + AWS DEV | Above plus SQS and S3 settings | Development queue/storage and configured search provider |

Restart API and worker after editing `.env`. Vite also needs a restart after changing `VITE_*` values. The UI separately displays discovery mode because real model inference does not make fictional research real.

## Containers

PostgreSQL alone: `docker compose up -d --wait postgres`.

To run the API and worker as containers, first stop the host API/worker processes to free port 8000, then run:

```powershell
docker compose --profile app build
docker compose run --rm api python -m alembic upgrade head
docker compose run --rm api python -m app.seed
docker compose --profile app up -d
```

Keep the React frontend on the host at port 5173. Container documents use the `documents` volume; host documents default to `.local/documents` relative to the API working directory. Use an absolute `LOCAL_STORAGE_PATH` if switching between working directories.

## Troubleshooting

- Docker pipe error: start Docker Desktop; ensure Linux containers and engine readiness.
- Port conflict: identify the listening application. The startup script intentionally preserves existing services.
- API readiness failure: check PostgreSQL and run `alembic upgrade head` from `backend`.
- Jobs stay queued: start the worker from the repository root using the same `.env` and database.
- Empty mock search: select one of the six seeded countries and the corresponding agent; mock search does not manufacture matches for other countries.
- Scripts disabled by local policy: run the documented commands manually or use your organization's approved PowerShell policy. No system policy changes are required by this repository.

No reset or volume-deletion script is provided. Existing business data is preserved.
