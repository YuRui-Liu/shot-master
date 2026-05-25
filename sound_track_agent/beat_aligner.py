"""卡点对齐纯算法：段落边界吸附 beat、爆点匹配 beat。可单测。"""
from __future__ import annotations


def _nearest(value: float, candidates: list[float]) -> float:
    return min(candidates, key=lambda c: abs(c - value))


def snap_boundaries_to_beats(boundaries: list[float],
                             beats: list[float],
                             max_shift: float = 0.3) -> list[float]:
    """把每个段落边界吸附到最近 beat；偏移超过 max_shift 则保留原值。

    beats 为空时原样返回。
    """
    if not beats:
        return list(boundaries)
    out: list[float] = []
    for b in boundaries:
        nb = _nearest(b, beats)
        out.append(nb if abs(nb - b) <= max_shift else b)
    return out


def align_accents(accents: list[float],
                  beats: list[float],
                  tolerance: float = 0.1) -> list[tuple[float, float]]:
    """把爆点匹配到容差内最近 beat，返回 (accent_t, beat_t) 对；无匹配则跳过。"""
    if not beats:
        return []
    pairs: list[tuple[float, float]] = []
    for a in accents:
        nb = _nearest(a, beats)
        if abs(nb - a) <= tolerance:
            pairs.append((a, nb))
    return pairs
