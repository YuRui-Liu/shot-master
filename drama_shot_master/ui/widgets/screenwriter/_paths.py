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


# ---------------------------------------------------------------------------
# 集级 helper（镜像 agent 端 paths.py）
# ---------------------------------------------------------------------------
import re as _re

EPISODE_ID_PATTERN_FE = _re.compile(r"^E[1-9]\d*$")


def is_valid_episode_id_fe(s: str) -> bool:
    return bool(EPISODE_ID_PATTERN_FE.match(s or ""))


def script_index_path_in(project_dir: Path) -> Path:
    return project_dir / "剧本.json"


def script_episode_path_in(project_dir: Path, episode_id: str) -> Path:
    return project_dir / f"剧本_{episode_id}.md"


def script_episode_read_path_in(project_dir: Path, episode_id: str) -> Path | None:
    primary = script_episode_path_in(project_dir, episode_id)
    if primary.is_file():
        return primary
    if episode_id == "E1":
        legacy = project_dir / "剧本.md"
        if legacy.is_file():
            return legacy
    return None


def storyboard_episode_path_in(project_dir: Path, episode_id: str) -> Path:
    return project_dir / f"分镜_{episode_id}.json"


def storyboard_episode_read_path_in(project_dir: Path, episode_id: str) -> Path | None:
    primary = storyboard_episode_path_in(project_dir, episode_id)
    if primary.is_file():
        return primary
    if episode_id == "E1":
        legacy = project_dir / "分镜.json"
        if legacy.is_file():
            return legacy
    return None


def episode_prompts_dir_in(project_dir: Path, episode_id: str) -> Path:
    return project_dir / "prompts" / episode_id
