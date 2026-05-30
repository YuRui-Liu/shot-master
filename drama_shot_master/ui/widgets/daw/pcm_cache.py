"""PCM 片段缓存：ffmpeg 解码任意音频 → 48k 立体声 float32 numpy + 懒缓存。

纯 numpy/subprocess，无 Qt。供实时混音引擎按播放头取样。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

SAMPLE_RATE = 48000
CHANNELS = 2

_EMPTY = np.zeros((0, CHANNELS), dtype=np.float32)


def decode_to_pcm(audio_path: str) -> np.ndarray:
    """ffmpeg 解码 → float32 (frames, 2) @48k。失败/空 → (0,2) 空数组（不抛）。"""
    if not audio_path or not Path(str(audio_path)).is_file():
        return _EMPTY.copy()
    cmd = ["ffmpeg", "-i", str(audio_path),
           "-f", "f32le", "-acodec", "pcm_f32le",
           "-ac", str(CHANNELS), "-ar", str(SAMPLE_RATE), "-"]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=False)
    except Exception:
        return _EMPTY.copy()
    if proc.returncode != 0 or not proc.stdout:
        return _EMPTY.copy()
    try:
        arr = np.frombuffer(proc.stdout, dtype=np.float32)
    except Exception:
        return _EMPTY.copy()
    if arr.size < CHANNELS:
        return _EMPTY.copy()
    # 丢弃不足一帧的尾部
    usable = (arr.size // CHANNELS) * CHANNELS
    return arr[:usable].reshape(-1, CHANNELS).copy()


class PcmCache:
    def __init__(self):
        self._cache: dict[str, np.ndarray] = {}

    def get(self, audio_path: str) -> np.ndarray:
        key = str(audio_path)
        pcm = self._cache.get(key)
        if pcm is None:
            pcm = decode_to_pcm(key)
            self._cache[key] = pcm
        return pcm

    def clear(self) -> None:
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)
