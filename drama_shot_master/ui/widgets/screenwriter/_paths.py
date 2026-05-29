"""主软件 UI 侧产物路径常量 + 兼容 helper（与 agent 端 paths.py 对齐）。"""
from __future__ import annotations

from pathlib import Path


IDEA_FILE = "创意.json"
IDEA_LEGACY = "idea.json"


def idea_file_in(project_dir: Path) -> Path | None:
    """优先 创意.json，兜底 idea.json。两个都不在返 None。"""
    primary = project_dir / IDEA_FILE
    if primary.is_file():
        return primary
    legacy = project_dir / IDEA_LEGACY
    if legacy.is_file():
        return legacy
    return None


def idea_exists_in(project_dir: Path) -> bool:
    """任一名字存在即视为创意已落盘。"""
    return idea_file_in(project_dir) is not None
