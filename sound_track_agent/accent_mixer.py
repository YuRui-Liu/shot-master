"""卡点感知混音纯算法 + 薄 I/O：泵感增益包络、段切目标时长。

build_pump_envelope / clip_targets / snapped_boundaries 为纯逻辑(可单测);
apply_pump 为 soundfile 薄包装。段切吸附复用 beat_aligner.snap_boundaries_to_beats。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from sound_track_agent.session import AccentPoint
from sound_track_agent.beat_aligner import snap_boundaries_to_beats


def build_pump_envelope(n_samples: int, sr: int, accents: list[AccentPoint],
                        *, strength: float,
                        attack: float = 0.012, release: float = 0.35):
    """基线 1.0 的逐样本增益。每个卡点处下压到 (1 - strength*intensity)：
    attack 秒内 1.0→floor、release 秒内 floor→1.0。多卡点重叠取逐样本 min。
    """
    n = int(n_samples)
    env = np.ones(max(0, n), dtype=np.float32)
    if strength <= 0 or not accents or n <= 0:
        return env
    a = max(1, int(round(attack * sr)))
    r = max(1, int(round(release * sr)))
    for ap in accents:
        depth = float(strength) * max(0.0, min(1.0, float(ap.intensity)))
        if depth <= 0:
            continue
        floor = 1.0 - depth
        idx = int(round(float(ap.t) * sr))
        if idx < 0 or idx >= n:
            continue
        a_lo = max(0, idx - a)
        if idx > a_lo:                                        # attack 段
            ramp = np.linspace(1.0, floor, idx - a_lo, endpoint=False,
                               dtype=np.float32)
            env[a_lo:idx] = np.minimum(env[a_lo:idx], ramp)
        env[idx] = min(env[idx], floor)                       # 谷底
        r_hi = min(n, idx + r + 1)
        if r_hi > idx + 1:                                    # release 段
            ramp = np.linspace(floor, 1.0, r_hi - (idx + 1), dtype=np.float32)
            env[idx + 1:r_hi] = np.minimum(env[idx + 1:r_hi], ramp)
    return env


def apply_pump(bgm_in, bgm_out, accents: list, *, strength: float,
               attack: float = 0.012, release: float = 0.35) -> Path:
    """读 wav → 乘泵感包络 → 写出。返回输出路径。读/写失败抛 RuntimeError。"""
    import soundfile as sf
    try:
        data, sr = sf.read(str(bgm_in), always_2d=True)       # (n, ch)
    except Exception as e:
        raise RuntimeError(f"apply_pump 读取失败 {bgm_in}: {e}")
    env = build_pump_envelope(data.shape[0], sr, accents, strength=strength,
                              attack=attack, release=release)
    out = (data * env[:, None]).astype(data.dtype, copy=False)
    bgm_out = Path(bgm_out)
    bgm_out.parent.mkdir(parents=True, exist_ok=True)
    try:
        sf.write(str(bgm_out), out, sr)
    except Exception as e:
        raise RuntimeError(f"apply_pump 写出失败 {bgm_out}: {e}")
    return bgm_out
