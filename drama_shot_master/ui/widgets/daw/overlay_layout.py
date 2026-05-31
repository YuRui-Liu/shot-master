"""动态叠加区行布局（纯函数，无 Qt）。

把 overlay 片段按 kind(bgm→sfx)×lane 算成可绘制的行布局，供 DawTrackView
渲染与 OverlayHeaderSection 头部行对齐复用。lane 划分复用 3a
OverlaySession 语义：同 kind 内 seg.lane 去重计数。
"""
from __future__ import annotations

from dataclasses import dataclass

_OV_LANE_H = 28
_OV_HEAD_H = 18
_OV_KIND_ORDER = ["bgm", "sfx"]


@dataclass
class OverlayRow:
    kind: str            # "bgm" | "sfx"
    lane: int            # 0,1,2…
    y: int               # 相对叠加区顶部（折叠头之下）的绝对 y
    segments: list       # 该 (kind,lane) 内的 OverlaySegment（按 t_start 排序）


def lanes_of(segments, kind: str) -> int:
    """某 kind 的 lane 数（lane 去重计数）。"""
    return len({s.lane for s in segments if s.kind == kind})


def lane_count(segments) -> int:
    """总 lane 数（各 kind lanes 求和）。"""
    return sum(lanes_of(segments, k) for k in _OV_KIND_ORDER)


def overlay_rows(segments, *, base_y: int, collapsed: bool):
    """返回 (rows, region_h)。

    - segments 空 → ([], 0)（连折叠头都不画，零视觉负担）。
    - collapsed 且非空 → ([], _OV_HEAD_H)（只占折叠头）。
    - 展开 → 按 kind(bgm→sfx)×lane 升序产出行，y 从 base_y+_OV_HEAD_H 起
      逐行 +_OV_LANE_H；region_h = _OV_HEAD_H + 行数×_OV_LANE_H。
    """
    if not segments:
        return [], 0
    if collapsed:
        return [], _OV_HEAD_H

    rows: list[OverlayRow] = []
    y = base_y + _OV_HEAD_H
    for kind in _OV_KIND_ORDER:
        lanes = sorted({s.lane for s in segments if s.kind == kind})
        for lane in lanes:
            segs = sorted(
                (s for s in segments if s.kind == kind and s.lane == lane),
                key=lambda s: s.t_start,
            )
            rows.append(OverlayRow(kind=kind, lane=lane, y=y, segments=segs))
            y += _OV_LANE_H

    region_h = _OV_HEAD_H + len(rows) * _OV_LANE_H
    return rows, region_h
