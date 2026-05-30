"""OverlayMixer：管理 N 条 audio-only 叠加轨，跟随主时钟（VideoPreviewWidget）。

每轨一个懒建的 QMediaPlayer+QAudioOutput。主时钟通过 sync(t) 驱动，
漂移 > _DRIFT_SEC 才 setPosition 纠偏，避免频繁 seek 卡顿。
"""
from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import QObject, QUrl


class _Track:
    def __init__(self):
        self.path: str | None = None
        self.enabled: bool = False
        self.volume: float = 1.0
        self.player = None       # QMediaPlayer（懒建）
        self.audio = None        # QAudioOutput

    def ensure_player(self, parent):
        if self.player is None:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            self.player = QMediaPlayer(parent)
            self.audio = QAudioOutput(parent)
            self.player.setAudioOutput(self.audio)
            self.audio.setVolume(self.volume)
        return self.player


class OverlayMixer(QObject):
    _DRIFT_SEC = 0.2

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tracks: dict[str, _Track] = {}

    @staticmethod
    def _should_resync(track_sec: float, master_sec: float) -> bool:
        return abs(float(track_sec) - float(master_sec)) > OverlayMixer._DRIFT_SEC

    def _track(self, name: str) -> _Track:
        t = self._tracks.get(name)
        if t is None:
            t = _Track()
            self._tracks[name] = t
        return t

    def set_track(self, name: str, path: str | None) -> None:
        t = self._track(name)
        if not path or not Path(str(path)).exists():
            t.path = None
            if t.player is not None:
                t.player.stop()
            return
        t.path = str(path)
        p = t.ensure_player(self)
        p.stop()
        p.setSource(QUrl.fromLocalFile(str(path)))

    def track_path(self, name: str) -> str | None:
        return self._track(name).path

    def set_enabled(self, name: str, on: bool) -> None:
        t = self._track(name)
        t.enabled = bool(on)
        if t.player is not None and t.audio is not None:
            t.audio.setMuted(not t.enabled)

    def is_enabled(self, name: str) -> bool:
        return self._track(name).enabled

    def set_volume(self, name: str, vol: float) -> None:
        v = max(0.0, min(1.5, float(vol)))
        t = self._track(name)
        t.volume = v
        if t.audio is not None:
            t.audio.setVolume(v)

    def volume(self, name: str) -> float:
        return self._track(name).volume

    def play(self) -> None:
        for t in self._tracks.values():
            if t.enabled and t.path and t.player is not None:
                t.player.play()

    def pause(self) -> None:
        for t in self._tracks.values():
            if t.player is not None:
                t.player.pause()

    def stop(self) -> None:
        for t in self._tracks.values():
            if t.player is not None:
                t.player.stop()

    def seek(self, t_sec: float) -> None:
        ms = max(0, int(round(float(t_sec) * 1000)))
        for t in self._tracks.values():
            if t.player is not None:
                t.player.setPosition(ms)

    def sync(self, t_sec: float) -> None:
        for t in self._tracks.values():
            if not (t.enabled and t.path and t.player is not None):
                continue
            cur = t.player.position() / 1000.0
            if self._should_resync(cur, t_sec):
                t.player.setPosition(max(0, int(round(t_sec * 1000))))
