"""镜头切点 → 叙事段落聚合。纯逻辑，可单测。"""
from __future__ import annotations

from dataclasses import dataclass

from sound_track_agent.session import EmotionTag, SegmentScore


@dataclass
class Shot:
    index: int
    t_start: float
    t_end: float

    @property
    def duration(self) -> float:
        return self.t_end - self.t_start


def plan_segments(shots: list[Shot], target: int = 4) -> list[SegmentScore]:
    """把相邻镜头按累计时长均衡聚合成 ~target 段。

    段数上限 = min(target, 5, 镜头数)；镜头很少时可少于 target（无硬下限）。
    贪心：理想段长 = 总时长 / 段数；累加镜头，超过理想段长即断段，
    故等长镜头下实际段数可能略少于上限（~target 为近似）。
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


def emotion_distance(a: EmotionTag, b: EmotionTag) -> float:
    """欧氏距离 on (valence_norm, arousal, intensity)。

    valence ∈[-1,1] 先映射到 [0,1] 与另两维同尺度。值域 [0, sqrt(3)]。
    """
    av = (a.valence + 1.0) / 2.0
    bv = (b.valence + 1.0) / 2.0
    d2 = ((av - bv) ** 2
          + (a.arousal - b.arousal) ** 2
          + (a.intensity - b.intensity) ** 2)
    return d2 ** 0.5


def _avg_emotion(a: EmotionTag, b: EmotionTag, n_a: int, n_b: int) -> EmotionTag:
    """按 shot 数加权平均三维数值；labels 取并集去重排序。"""
    total = n_a + n_b
    return EmotionTag(
        labels=sorted(set(a.labels) | set(b.labels)),
        valence=(a.valence * n_a + b.valence * n_b) / total,
        arousal=(a.arousal * n_a + b.arousal * n_b) / total,
        intensity=(a.intensity * n_a + b.intensity * n_b) / total,
    )


def cluster_by_emotion(shots: list[Shot], emotions: list[EmotionTag], *,
                       max_segments: int = 5,
                       merge_threshold: float = 0.25) -> list[SegmentScore]:
    """邻接 agglomerative 聚合。每 shot 起为 1 cluster，重复合并相邻距离最小的对：

    停止条件：len(clusters) ≤ max_segments AND min_adjacent_gap ≥ merge_threshold。

    返回 list[SegmentScore]，每段 emotion 已填、status="tagged"。
    """
    if not shots:
        raise ValueError("cluster_by_emotion 需要至少 1 个镜头")
    if len(shots) != len(emotions):
        raise ValueError("shots/emotions 长度不一致")

    clusters: list[list[int]] = [[i] for i in range(len(shots))]
    cluster_emo: list[EmotionTag] = list(emotions)

    while True:
        if len(clusters) == 1:
            break

        # 停止条件：len <= max_segments AND min_gap >= threshold
        gaps = [emotion_distance(cluster_emo[i], cluster_emo[i + 1])
                for i in range(len(clusters) - 1)]
        min_gap = min(gaps)

        if len(clusters) <= max_segments and min_gap >= merge_threshold:
            break

        # 找到相邻距离最小的对，合并
        k = gaps.index(min_gap)
        n_a, n_b = len(clusters[k]), len(clusters[k + 1])
        merged_shots = clusters[k] + clusters[k + 1]
        merged_emo = _avg_emotion(cluster_emo[k], cluster_emo[k + 1], n_a, n_b)
        clusters = clusters[:k] + [merged_shots] + clusters[k + 2:]
        cluster_emo = cluster_emo[:k] + [merged_emo] + cluster_emo[k + 2:]

    out: list[SegmentScore] = []
    for i, shot_ids in enumerate(clusters):
        first = shots[shot_ids[0]]
        last = shots[shot_ids[-1]]
        out.append(SegmentScore(
            index=i, t_start=first.t_start, t_end=last.t_end,
            shot_ids=list(shot_ids),
            emotion=cluster_emo[i],
            status="tagged",
        ))
    return out
