"""每用户可写目录（license 文件、dev 机器码回退）。"""
from __future__ import annotations

import os
from pathlib import Path


def user_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:                                   # Windows
        d = Path(base) / "DramaShotMaster"
    else:
        d = Path.home() / ".drama_shot_master"
    d.mkdir(parents=True, exist_ok=True)
    return d
