#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test -f .env || cp .env.example .env
test -d .venv || python3 -m venv .venv
.venv/bin/python -m pip install -e './backend[dev]'
docker compose up -d --wait postgres
(cd backend && ../.venv/bin/python -m alembic upgrade head && ../.venv/bin/python -m app.seed)
(cd frontend && npm ci)
echo 'Setup complete. Run bash scripts/run-local.sh.'
