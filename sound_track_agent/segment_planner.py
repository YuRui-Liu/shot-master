"""镜头切点 → 叙事段落聚合。纯逻辑，可单测。"""
from __future__ import annotations

from dataclasses import dataclass

from sound_track_agent.session import SegmentScore


@dataclass
class Shot:
    index: int
    t_start: float
    t_end: float

    @property
    def duration(self) -> float:
        return self.t_end - self.t_start


def plan_segments(shots: list[Shot], target: int = 4) -> list[SegmentScore]:
    """把相邻镜头按累计时长均衡聚合成 ~target 段（clamp 3-5、且不超过镜头数）。

    贪心：理想段长 = 总时长 / 段数；累加镜头，超过理想段长即断段。
    """
    if not shots:
        raise ValueError("plan_segments 需要至少 1 个镜头")
    n_seg = max(1, min(target, len(shots)))
    n_seg = min(n_seg, 5)
    total = sum(s.duration for s in shots)
    ideal = total / n_seg

    groups: list[list[Shot]] = []
    cur: list[Shot] = []
    cur_dur = 0.0
    for shot in shots:
        cur.append(shot)
        cur_dur += shot.duration
        remaining_segs = n_seg - len(groups) - 1
        remaining_shots = len(shots) - sum(len(g) for g in groups) - len(cur)
        if (cur_dur >= ideal and remaining_segs >= 1
                and remaining_shots >= remaining_segs):
            groups.append(cur)
            cur, cur_dur = [], 0.0
    if cur:
        groups.append(cur)

    segs: list[SegmentScore] = []
    for i, g in enumerate(groups):
        segs.append(SegmentScore(
            index=i,
            t_start=g[0].t_start,
            t_end=g[-1].t_end,
            shot_ids=[s.index for s in g],
        ))
    return segs
