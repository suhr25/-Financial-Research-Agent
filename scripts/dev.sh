#!/usr/bin/env bash
# Convenience script for local development on macOS/Linux/WSL.
# Usage: from the project root, run:  ./scripts/dev.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
./.venv/bin/pip install --quiet -r requirements.txt

if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "Created .env from .env.example (DEMO_MODE=true by default)."
fi

./.venv/bin/python -m uvicorn app.main:app --reload --port 8000
