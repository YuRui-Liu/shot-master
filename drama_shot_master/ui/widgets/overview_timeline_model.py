"""数据派生：4 个数据源 → 统一 _Cue 列表。无 IO，可单测。"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal


@dataclass
class _Cue:
    track: Literal["video", "bgm", "sfx", "dialogue"]
    t_start: float
    t_end: float
    label: str
    seg_index: int
