"""实时混音核：给定播放头 + 活跃片段 → 叠加出输出缓冲。纯 numpy 无副作用。"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class ActiveClip:
    pcm: np.ndarray      # (frames, 2) float32
    t_start: float       # 片段在时间线上的起点（秒）
    volume: float = 1.0


def mix_frame(clips, playhead_sec: float, n_frames: int,
              sample_rate: int = 48000) -> np.ndarray:
    """混出从 playhead_sec 起 n_frames 帧立体声 (n_frames, 2) float32。hard clip [-1,1]。"""
    out = np.zeros((n_frames, 2), dtype=np.float32)
    win0 = int(round(playhead_sec * sample_rate))      # 窗口起始绝对帧
    for c in clips:
        pcm = c.pcm
        m = pcm.shape[0]
        if m == 0:
            continue
        clip0 = int(round(c.t_start * sample_rate))     # clip 起始绝对帧
        # clip 覆盖绝对帧 [clip0, clip0+m)；窗口绝对帧 [win0, win0+n_frames)
        lo = max(win0, clip0)
        hi = min(win0 + n_frames, clip0 + m)
        if hi <= lo:
            continue
        out_off = lo - win0          # 写入 out 的起点
        clip_off = lo - clip0        # 读 pcm 的起点
        k = hi - lo
        seg = pcm[clip_off:clip_off + k]
        if c.volume != 1.0:
            seg = seg * np.float32(c.volume)
        out[out_off:out_off + k] += seg
    np.clip(out, -1.0, 1.0, out=out)
    return out
