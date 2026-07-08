#!/usr/bin/env bash
set -euo pipefail

RELEASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="${HOME}/asr_test"

mkdir -p "${TARGET_DIR}/prompts"
mkdir -p "${TARGET_DIR}/static"

cp "${RELEASE_DIR}/emotender_backend.py" "${TARGET_DIR}/emotender_backend.py"
cp "${RELEASE_DIR}/prompts/drink_mapping.json" "${TARGET_DIR}/prompts/drink_mapping.json"
cp "${RELEASE_DIR}/requirements.txt" "${TARGET_DIR}/requirements.txt"
cp "${RELEASE_DIR}/static/index.html" "${TARGET_DIR}/static/index.html"

if [ ! -f "${TARGET_DIR}/.env" ]; then
  cp "${RELEASE_DIR}/.env.example" "${TARGET_DIR}/.env"
  echo "已创建 ${TARGET_DIR}/.env，请填写 LLM_BASE_URL、LLM_API_KEY、LLM_MODEL。"
fi

cd "${TARGET_DIR}"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip

python - <<'PY' || python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
try:
    import torch
    import torchaudio
except Exception:
    raise SystemExit(1)
print("torch and torchaudio already installed")
PY

python -m pip install -r requirements.txt

python -m py_compile emotender_backend.py
python -m json.tool prompts/drink_mapping.json >/dev/null

echo "部署完成。"
echo "下一步："
echo "1. 确认 ${TARGET_DIR}/.env 已填写真实中转站配置。"
echo "2. 运行：cd ${TARGET_DIR} && source .venv/bin/activate && uvicorn emotender_backend:app --host 0.0.0.0 --port 8000"
