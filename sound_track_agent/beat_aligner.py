"""卡点对齐纯算法：段落边界吸附 beat、爆点匹配 beat。可单测。"""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


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


def _plan_alignment(beats: list[float], accents: list,
                    max_stretch: float, big_threshold: float) -> list[tuple[int, float, float]]:
    """纯逻辑：选哪些 big-accent 能局部拉伸对齐到 beat。

    返回 list of (accent_idx, accent_t, beat_t) 按时间升序。

    算法：
    - 只考虑 intensity >= big_threshold 的 accent（big accent）
    - 对每个 big accent，找最大的 b <= t（前向 beat）且未被用过
    - factor = (b - prev_b) / (t - prev_t)：librosa time_stretch rate
      rate > 1 → 加速（源段比目标长）；rate < 1 → 减速
    - |factor - 1.0| > max_stretch 则跳过（超 ±max_stretch 拉伸上限）
    """
    big = sorted([(i, float(a.t)) for i, a in enumerate(accents)
                  if float(a.intensity) >= big_threshold],
                 key=lambda x: x[1])
    aligned = []
    used: set[float] = set()
    prev_t, prev_b = 0.0, 0.0
    for (i, t) in big:
        # 只取 b <= t 且未被用且在上一个锚点之后的 beat
        candidates = [b for b in beats
                      if b <= t and b not in used and b > prev_b]
        if not candidates:
            continue
        b = max(candidates)
        # 段长必须均大于 0 才能计算 factor
        if (t - prev_t) <= 0:
            continue
        factor = (b - prev_b) / (t - prev_t)
        if abs(factor - 1.0) > max_stretch:
            continue
        aligned.append((i, t, b))
        used.add(b)
        prev_t, prev_b = t, b
    return aligned


def _chunks_from_plan(aligned, total_dur: float) -> list[tuple[str, float, float, float]]:
    """纯逻辑：对齐计划 → 拉伸 chunks。

    返回 list of (kind, src_start, src_end, target_dur):
      - "stretch" 段：源音频 [src_start, src_end] 拉/压到 target_dur 秒
      - "tail" 段：末段原速保留（target_dur 仅供参考，实际按源长度）
    """
    chunks = []
    prev_t, prev_b = 0.0, 0.0
    for (_, t, b) in aligned:
        chunks.append(("stretch", prev_b, b, t - prev_t))
        prev_t, prev_b = t, b
    chunks.append(("tail", prev_b, float(total_dur),
                   float(total_dur) - prev_t))
    return chunks


def align_beats_to_accents(bgm_path, accents: list, *,
                           max_stretch: float = 0.10,
                           big_threshold: float = 0.7,
                           out_path=None,
                           extractor=None, stretcher=None,
                           reader=None, writer=None) -> tuple[Path, frozenset[int]]:
    """把音乐重拍局部拉伸到大爆点；返回 (out_path, aligned_indices)。

    注入点（缺省用 librosa + soundfile）：
      - extractor(path) -> list[float]       默认 extract_beats
      - reader(path)    -> (np.ndarray, sr)  默认 soundfile.read(always_2d=True)
      - writer(path, samples, sr) -> None    默认 soundfile.write
      - stretcher(y, rate) -> y_new          默认 librosa.effects.time_stretch

    失败降级（librosa 不可用 / beats 空 / 任意异常）→ 返回 (bgm_path, frozenset())。
    """
    try:
        import numpy as np

        if extractor is None:
            extractor = extract_beats
        beats = list(extractor(bgm_path) or [])
        if not beats:
            return Path(bgm_path), frozenset()

        if reader is None:
            import soundfile as sf
            reader = lambda p: sf.read(str(p), always_2d=True)
        if writer is None:
            import soundfile as sf
            writer = lambda p, d, s: sf.write(str(p), d, s)
        if stretcher is None:
            import librosa
            stretcher = lambda y, rate: librosa.effects.time_stretch(y, rate=rate)

        data, sr = reader(bgm_path)
        if data is None or sr is None or data.shape[0] == 0:
            return Path(bgm_path), frozenset()
        total_dur = data.shape[0] / float(sr)

        plan = _plan_alignment(beats, accents, max_stretch, big_threshold)
        if not plan:
            return Path(bgm_path), frozenset()

        chunks = _chunks_from_plan(plan, total_dur)
        out_path = Path(out_path) if out_path else Path(bgm_path).with_suffix(
            ".aligned.wav")

        pieces = []
        for kind, src_start, src_end, target in chunks:
            s = max(0, int(round(src_start * sr)))
            e = min(data.shape[0], int(round(src_end * sr)))
            seg = data[s:e]
            if seg.shape[0] == 0:
                continue
            if kind == "stretch" and target > 0:
                rate = (src_end - src_start) / target
                if seg.ndim == 1 or seg.shape[1] == 1:
                    mono = seg.reshape(-1).astype("float64", copy=False)
                    out = stretcher(mono, rate=rate)
                    seg = out.reshape(-1, 1) if data.ndim == 2 else out
                else:
                    chans = [stretcher(np.ascontiguousarray(seg[:, c]).astype(
                        "float64", copy=False), rate=rate)
                        for c in range(seg.shape[1])]
                    L = min(len(c) for c in chans)
                    seg = np.stack([c[:L] for c in chans], axis=1)
            pieces.append(seg)

        result = np.concatenate(pieces, axis=0)
        writer(out_path, result.astype(data.dtype, copy=False), sr)
        return out_path, frozenset(idx for (idx, _, _) in plan)
    except Exception:
        log.warning("align_beats_to_accents 降级：%s", bgm_path, exc_info=True)
        return Path(bgm_path), frozenset()
