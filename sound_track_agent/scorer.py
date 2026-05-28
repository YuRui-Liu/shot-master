"""候选 BGM 打分：health / headroom / beat → 总分。核心数学纯函数，可单测。

score_candidate 薄读音频（soundfile）；beat 用 librosa（缺失则降级中性）。
读取失败由调用方降级为 None。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

DEFAULT_WEIGHTS = {"health": 0.5, "headroom": 0.3, "beat": 0.2}


@dataclass
class CandidateScore:
    total: float
    health: float
    headroom: float
    beat: float


def health_score(samples: np.ndarray, sr: int, expected_dur: float) -> float:
    """[0,1]。惩罚削波 / 近静音 / 过短 / NaN。samples 单声道 float[-1,1]。"""
    if samples.size == 0 or not np.all(np.isfinite(samples)):
        return 0.0
    clip_frac = float(np.mean(np.abs(samples) >= 0.999))
    rms = float(np.sqrt(np.mean(samples ** 2)))
    dur = samples.size / sr if sr else 0.0
    score = 1.0
    score -= min(1.0, clip_frac * 10.0)                 # 10% 削波即清零该项
    if rms < 0.01:                                      # 近静音
        score -= 0.8
    if expected_dur > 0 and dur < expected_dur * 0.5:   # 远短于期望
        score -= 0.5
    return max(0.0, min(1.0, score))


def headroom_score(samples: np.ndarray, sr: int) -> float:
    """[0,1]。语音频段(300-3400Hz)能量占比越低分越高（给人声让路）。"""
    if samples.size == 0 or sr <= 0:
        return 0.5
    spec = np.abs(np.fft.rfft(samples))
    freqs = np.fft.rfftfreq(samples.size, 1.0 / sr)
    total = float(np.sum(spec ** 2)) + 1e-9
    band = (freqs >= 300) & (freqs <= 3400)
    ratio = float(np.sum(spec[band] ** 2)) / total
    return max(0.0, min(1.0, 1.0 - ratio))


def beat_score(samples: np.ndarray, sr: int) -> float:
    """[0,1]。librosa onset 自相关清晰度；librosa 不可用/异常/空输入 → 中性 0.5。"""
    if samples is None or len(samples) == 0 or sr <= 0:
        return 0.5
    try:
        import librosa
        onset = librosa.onset.onset_strength(y=samples, sr=sr)
        if onset.size == 0:
            return 0.5
        ac = librosa.autocorrelate(onset)
        if ac.size < 2 or ac[0] <= 0:
            return 0.5
        return max(0.0, min(1.0, float(np.max(ac[1:]) / ac[0])))
    except Exception:
        return 0.5


def score_candidate(path, *, expected_dur: float = 0.0,
                    weights: dict | None = None) -> CandidateScore:
    """读音频 → 三项 → 加权总分。读失败抛异常（调用方降级为 None）。"""
    import soundfile as sf
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    data, sr = sf.read(str(path), always_2d=True)
    mono = data.mean(axis=1).astype("float64")
    h = health_score(mono, sr, expected_dur)
    hr = headroom_score(mono, sr)
    b = beat_score(mono, sr)
    total = (weights["health"] * h + weights["headroom"] * hr
             + weights["beat"] * b)
    return CandidateScore(total=total, health=h, headroom=hr, beat=b)


def pick_best(candidates) -> int:
    """返回 score 最高候选的下标；全 None → 0。candidates 为 BGMCandidate 列表。"""
    best, best_i, seen = -1.0, 0, False
    for i, c in enumerate(candidates):
        s = getattr(c, "score", None)
        if s is not None:
            seen = True
            if s > best:
                best, best_i = s, i
    return best_i if seen else 0
