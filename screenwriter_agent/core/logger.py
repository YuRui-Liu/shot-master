"""按 stage 把单次 LLM 调用记录到 <project_dir>/.agent/logs/<stage>_<ts>.json。
spec §6.5。"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .atomic_write import atomic_write_text


def log_stage_call(project_dir: Path, stage: str, payload: dict[str, Any]) -> Path:
    """落盘一次调用日志，返回日志路径。payload 应已含 model / duration_ms 等字段；
    本函数补 ts/stage 字段并写到 .agent/logs/<stage>_<ts>.json。"""
    project_dir = Path(project_dir)
    logs_dir = project_dir / ".agent" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%S", time.localtime())
    log_path = logs_dir / f"{stage}_{ts}.json"
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
              "stage": stage, **payload}
    atomic_write_text(log_path, json.dumps(record, ensure_ascii=False, indent=2))
    return log_path
