#!/bin/bash
# Spin up the SIM Price Tracker locally.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Create / reuse a local virtualenv so we don't pollute system Python
if [ ! -d ".venv" ]; then
  echo "[setup] creating virtualenv..."
  python3 -m venv .venv
fi
source .venv/bin/activate

echo "[setup] installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r backend/requirements.txt

mkdir -p backend/data

echo "[run] starting FastAPI on http://127.0.0.1:8000"
cd backend
exec python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
