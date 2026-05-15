#!/usr/bin/env bash
set -e

if [ ! -f .env ]; then
  echo "[WARN] .env not found. Copying .env.example..."
  cp .env.example .env
  echo "请编辑 .env 填写 API Key 后再次运行"
  exit 1
fi

if ! python -c "import shot_master" 2>/dev/null; then
  echo "[INFO] Installing local shot-master..."
  pip install -e ../../shot-master
fi

if ! python -c "from PySide6.QtWidgets import QApplication" 2>/dev/null; then
  echo "[INFO] Installing project dependencies..."
  pip install -e .
fi

python -m app.main
