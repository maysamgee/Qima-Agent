#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test -f .env || cp .env.example .env
docker compose up -d --wait postgres
(cd backend && ../.venv/bin/python -m alembic upgrade head && ../.venv/bin/python -m app.seed)
mkdir -p .local
(.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log >.local/api.log 2>&1) &
api_pid=$!
(.venv/bin/python -m worker.app.main >.local/worker.log 2>&1) &
worker_pid=$!
(cd frontend && npm run dev >../.local/frontend.log 2>&1) &
web_pid=$!
trap 'kill "$api_pid" "$worker_pid" "$web_pid" 2>/dev/null || true' EXIT INT TERM
echo 'Frontend http://localhost:5173 | API http://localhost:8000/docs. Press Ctrl+C to stop.'
wait
