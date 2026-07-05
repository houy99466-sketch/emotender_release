#!/usr/bin/env bash
set -euo pipefail

cd "${HOME}/asr_test"
source .venv/bin/activate
uvicorn emotender_backend:app --host 0.0.0.0 --port 8000
