#!/usr/bin/env bash
set -e

if [ ! -f .env ]; then
  echo "[WARN] .env 不存在，从 .env.example 创建"
  cp .env.example .env
  echo "请编辑 .env 填写 API Key 后再次运行"
  exit 1
fi

if ! python -c "import shot_master" 2>/dev/null; then
  echo "[INFO] 安装本地 shot-master..."
  pip install -e ../../shot-master
fi

if ! python -c "import fastapi" 2>/dev/null; then
  echo "[INFO] 安装本项目依赖..."
  pip install -e .
fi

python -m app.main
