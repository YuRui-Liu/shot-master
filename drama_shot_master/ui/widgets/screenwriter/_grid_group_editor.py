"""分镜图提示词 — 手动分组编辑器 + 纯函数。

纯函数无 Qt 依赖，便于单测；_GridGroupEditor 是表格 UI（后续任务追加）。
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QComboBox, QPushButton, QLabel, QHeaderView,
)

_MODE_LABELS = [("single", "单帧"), ("4", "四宫格"), ("9", "九宫格")]
_CAP = {"single": 1, "4": 4, "9": 9}


def group_capacity(grid_mode: str) -> int:
    return _CAP.get(grid_mode, 9)


def auto_fit_mode(count: int) -> str:
    """容纳 count 镜的最小容量模式。"""
    if count <= 1:
        return "single"
    if count <= 4:
        return "4"
    return "9"


def default_groups(shot_ids: list[str]) -> list[dict]:
    """按 9 切块；每组 grid_mode = auto_fit_mode(组镜头数)。"""
    out: list[dict] = []
    for i in range(0, len(shot_ids), 9):
        chunk = shot_ids[i:i + 9]
        out.append({"grid_mode": auto_fit_mode(len(chunk)),
                    "shot_ids": list(chunk)})
    return out


def group_is_valid(group: dict) -> bool:
    ids = group.get("shot_ids") or []
    return 0 < len(ids) <= group_capacity(group.get("grid_mode", "9"))
