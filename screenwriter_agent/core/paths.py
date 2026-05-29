"""项目内产物文件路径——含旧名兼容。

创意阶段产物历史上叫 idea.json（agent 内部命名）；UI 侧任务栏/上游 banner
检查的是 创意.json（中文一致性，与 剧本.md/分镜.json 对齐）。
本模块统一对外暴露：写入用 创意.json，读取两个名字都接受。
"""
from __future__ import annotations

import re as _re
from pathlib import Path

IDEA_FILE_NAME = "创意.json"
IDEA_LEGACY_NAME = "idea.json"


def idea_write_path(project_dir: Path) -> Path:
    """新落盘路径——统一用中文名 创意.json。"""
    return project_dir / IDEA_FILE_NAME


def idea_read_path(project_dir: Path) -> Path | None:
    """读取——优先新名，兜底旧名。两个都不在返 None。"""
    primary = project_dir / IDEA_FILE_NAME
    if primary.is_file():
        return primary
    legacy = project_dir / IDEA_LEGACY_NAME
    if legacy.is_file():
        return legacy
    return None


def idea_exists(project_dir: Path) -> bool:
    """任一名字存在即认作创意已落盘。"""
    return idea_read_path(project_dir) is not None


EPISODE_ID_PATTERN = _re.compile(r"^E([1-9]\d*)$")


def is_valid_episode_id(s: str) -> bool:
    """1-based 集 ID 校验：E1, E2, ..."""
    return bool(EPISODE_ID_PATTERN.match(s or ""))


def script_index_path(project_dir: Path) -> Path:
    """剧本集索引路径（写入用，统一 剧本.json）。"""
    return project_dir / "剧本.json"


def script_episode_path(project_dir: Path, episode_id: str) -> Path:
    """写入路径：剧本_E{id}.md。"""
    return project_dir / f"剧本_{episode_id}.md"


def script_episode_read_path(project_dir: Path, episode_id: str) -> Path | None:
    """读取路径：优先 剧本_E{id}.md，兜底 旧的单文件 剧本.md（仅 E1 时）。"""
    primary = script_episode_path(project_dir, episode_id)
    if primary.is_file():
        return primary
    if episode_id == "E1":
        legacy = project_dir / "剧本.md"
        if legacy.is_file():
            return legacy
    return None


def storyboard_episode_path(project_dir: Path, episode_id: str) -> Path:
    """写入路径：分镜_E{id}.json。"""
    return project_dir / f"分镜_{episode_id}.json"


def storyboard_episode_read_path(project_dir: Path, episode_id: str) -> Path | None:
    """读取路径：优先 分镜_E{id}.json，兜底 旧的单文件 分镜.json（仅 E1 时）。"""
    primary = storyboard_episode_path(project_dir, episode_id)
    if primary.is_file():
        return primary
    if episode_id == "E1":
        legacy = project_dir / "分镜.json"
        if legacy.is_file():
            return legacy
    return None


def episode_prompts_dir(project_dir: Path, episode_id: str) -> Path:
    """prompts/E{id}/ 目录（不保证存在）。"""
    return project_dir / "prompts" / episode_id
