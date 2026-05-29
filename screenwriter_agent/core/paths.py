"""项目内产物文件路径——含旧名兼容。

创意阶段产物历史上叫 idea.json（agent 内部命名）；UI 侧任务栏/上游 banner
检查的是 创意.json（中文一致性，与 剧本.md/分镜.json 对齐）。
本模块统一对外暴露：写入用 创意.json，读取两个名字都接受。
"""
from __future__ import annotations

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
