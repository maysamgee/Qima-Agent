#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
(cd backend && ../.venv/bin/python -m ruff check app tests ../worker && ../.venv/bin/python -m mypy app ../worker/app && ../.venv/bin/python -m pytest)
(cd frontend && npm run lint && npm test && npm run build)
