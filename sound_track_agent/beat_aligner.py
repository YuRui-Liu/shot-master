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


def extract_beats(audio_path) -> list[float]:
    """用 librosa 提取音乐节拍时间戳（秒，升序）。

    供 snap_boundaries_to_beats / align_accents 作为 beats 输入。
    提取失败/静音/异常 → 返回 []（降级为不卡点，不中断管线）。
    """
    try:
        # Import locally to avoid lazy loader issues with pytest stubs
        import librosa
        import librosa.core.audio
        import librosa.beat

        y, sr = librosa.load(str(audio_path), sr=None, mono=True)
        if y is None or len(y) == 0:
            return []
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        times = librosa.frames_to_time(beat_frames, sr=sr)
        return sorted([float(t) for t in times])
    except Exception:
        return []
