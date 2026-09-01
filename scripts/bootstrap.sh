#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3.11}"
ENV_DIR="${ENV_DIR:-.venv}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "找不到 $PYTHON_BIN。请安装 Python 3.11，或使用 PYTHON_BIN 指定 Python 3.10/3.12/3.13。" >&2
  exit 1
fi

"$PYTHON_BIN" scripts/check_python.py
"$PYTHON_BIN" -m venv "$ENV_DIR"
# shellcheck disable=SC1090
source "$ENV_DIR/bin/activate"
python scripts/check_python.py
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo "环境已创建：$ENV_DIR。激活命令：source $ENV_DIR/bin/activate"
