"""实时混音输出引擎：overlay 片段 → 播放头驱动 → pull 混音帧 + sounddevice 输出。

两层：MixStreamEngine（纯逻辑拉帧，全单测）+ MixStreamOutput（设备适配，
import/开流失败优雅降级）。视频为主时钟，set_playhead 由 positionChanged 驱动。
"""
from __future__ import annotations

import numpy as np

from drama_shot_master.ui.widgets.daw.pcm_cache import PcmCache, SAMPLE_RATE
from drama_shot_master.ui.widgets.daw.mix_core import ActiveClip, mix_frame


class MixStreamEngine:
    def __init__(self, pcm_cache=None, sample_rate: int = SAMPLE_RATE):
        self._cache = pcm_cache if pcm_cache is not None else PcmCache()
        self._sr = int(sample_rate)
        self._clips: list = []
        self._playhead = 0.0
        self._frames_since = 0
        self._playing = False

    def set_segments(self, segs) -> None:
        clips = []
        for s in segs or []:
            if not getattr(s, "enabled", True):
                continue
            path = getattr(s, "audio_path", "") or ""
            if not path:
                continue
            pcm = self._cache.get(path)
            if pcm.shape[0] == 0:
                continue
            clips.append(ActiveClip(pcm=pcm,
                                    t_start=float(getattr(s, "t_start", 0.0)),
                                    volume=float(getattr(s, "volume", 1.0))))
        self._clips = clips

    def clip_count(self) -> int:
        return len(self._clips)

    def set_playhead(self, t_sec: float) -> None:
        self._playhead = float(t_sec)
        self._frames_since = 0

    def play(self) -> None:
        self._playing = True

    def pause(self) -> None:
        self._playing = False

    def current_playhead(self) -> float:
        return self._playhead + self._frames_since / self._sr

    def pull(self, n_frames: int) -> np.ndarray:
        if not self._playing:
            return np.zeros((n_frames, 2), dtype=np.float32)
        out = mix_frame(self._clips, self.current_playhead(), n_frames, self._sr)
        self._frames_since += n_frames
        return out


class MixStreamOutput:
    """sounddevice OutputStream 包装。import/开流失败 → available=False 降级。"""

    def __init__(self, engine, sample_rate: int = SAMPLE_RATE, channels: int = 2):
        self._engine = engine
        self._stream = None
        self.available = False
        try:
            import sounddevice as sd
            self._stream = sd.OutputStream(
                samplerate=sample_rate, channels=channels,
                dtype="float32", callback=self._cb)
            self.available = True
        except Exception:
            self._stream = None
            self.available = False

    def _cb(self, outdata, frames, time_info, status):  # pragma: no cover
        outdata[:] = self._engine.pull(frames)

    def start(self) -> None:
        if self.available and self._stream is not None:
            try:
                self._stream.start()
            except Exception:
                self.available = False

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                pass

    def close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.close()
            except Exception:
                pass
            self._stream = None
