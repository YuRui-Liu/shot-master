"""Core dataclass specifications for splitter and combiner."""
from dataclasses import dataclass, field
from enum import Enum


@dataclass(frozen=True)
class Margins:
    """源图四方向外边距（像素）。"""
    top: int = 0
    right: int = 0
    bottom: int = 0
    left: int = 0

    @classmethod
    def uniform(cls, value: int) -> "Margins":
        return cls(value, value, value, value)


@dataclass(frozen=True)
class AspectRatio:
    """w:h 目标比例。AspectRatio(0, 0) 视为 Auto（不裁剪）。"""
    w: int
    h: int

    @classmethod
    def auto(cls) -> "AspectRatio":
        return cls(0, 0)

    def is_auto(self) -> bool:
        return self.w == 0 or self.h == 0

    @property
    def value(self) -> float:
        return self.w / self.h


class ScaleMode(str, Enum):
    LETTERBOX = "letterbox"
    CROP = "crop"
    STRETCH = "stretch"


@dataclass(frozen=True)
class GridSpec:
    """描述源图网格布局。splitter 的唯一参数对象。"""
    src_rows: int
    src_cols: int
    sub_rows: int
    sub_cols: int
    margins: Margins = field(default_factory=Margins)
    gap: int = 0
    target_aspect: AspectRatio = field(default_factory=AspectRatio.auto)


@dataclass(frozen=True)
class CombineSpec:
    """描述合并目标。combiner 的唯一参数对象。"""
    target_rows: int
    target_cols: int
    gap: int = 0
    target_aspect: AspectRatio = field(default_factory=AspectRatio.auto)
    scale_mode: ScaleMode = ScaleMode.LETTERBOX
