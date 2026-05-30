"""OverlayMixer：管理 N 条 audio-only 叠加轨，跟随主时钟（VideoPreviewWidget）。

两种轨模式（零渲染，纯实时同时播放）：
  - 单文件轨   set_track(name, path)         —— 候选试听用
  - 时间表轨   set_schedule(name, clips)     —— 配乐/音效叠加用：clips 是
                [(t_start, t_end, path), ...]，sync(t) 时按播放头切到对应段
                的 mp3 并定位到段内偏移；段间空隙暂停。**不做任何 ffmpeg 合成**。

每轨一个懒建的 QMediaPlayer+QAudioOutput。漂移 > _DRIFT_SEC 才 setPosition 纠偏。
"""
from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import QObject, QUrl


class _Track:
    def __init__(self):
        self.path: str | None = None                 # 单文件轨
        self.schedule: list[tuple] | None = None      # 时间表轨 [(t0,t1,path)]
        self.active_idx: int = -1
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
            self.audio.setMuted(not self.enabled)
        return self.player


class OverlayMixer(QObject):
    _DRIFT_SEC = 0.2

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tracks: dict[str, _Track] = {}
        self._playing: bool = False
        self._last_t: float = 0.0

    @staticmethod
    def _should_resync(track_sec: float, master_sec: float) -> bool:
        return abs(float(track_sec) - float(master_sec)) > OverlayMixer._DRIFT_SEC

    @staticmethod
    def _active_clip_index(schedule, t: float) -> int:
        """返回包含时间 t 的 clip 下标；不在任何 clip 内 → -1。"""
        if not schedule:
            return -1
        for i, (t0, t1, _p) in enumerate(schedule):
            if float(t0) <= t < float(t1):
                return i
        return -1

    def _track(self, name: str) -> _Track:
        t = self._tracks.get(name)
        if t is None:
            t = _Track()
            self._tracks[name] = t
        return t

    # ── 单文件轨（试听）────────────────────────────────────────────────

    def set_track(self, name: str, path: str | None) -> None:
        t = self._track(name)
        t.schedule = None
        t.active_idx = -1
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

    # ── 时间表轨（叠加播放，零渲染）────────────────────────────────────

    def set_schedule(self, name: str, clips) -> None:
        """clips: [(t_start, t_end, path), ...]，仅保留存在的文件。"""
        t = self._track(name)
        t.path = None
        t.active_idx = -1
        valid = [(float(a), float(b), str(p)) for (a, b, p) in (clips or [])
                 if p and Path(str(p)).exists()]
        t.schedule = valid or None
        if t.schedule:
            t.ensure_player(self)
        elif t.player is not None:
            t.player.stop()

    def schedule_len(self, name: str) -> int:
        s = self._track(name).schedule
        return len(s) if s else 0

    # ── 启用/音量 ──────────────────────────────────────────────────────

    def set_enabled(self, name: str, on: bool) -> None:
        t = self._track(name)
        t.enabled = bool(on)
        if t.player is not None and t.audio is not None:
            t.audio.setMuted(not t.enabled)
        if not t.enabled and t.player is not None:
            t.player.pause()

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

    # ── 播放控制 ───────────────────────────────────────────────────────

    def play(self) -> None:
        self._playing = True
        for name, t in self._tracks.items():
            if not (t.enabled and t.player is not None):
                continue
            if t.schedule is not None:
                self._activate_scheduled(t, self._last_t)
            elif t.path:
                t.player.play()

    def pause(self) -> None:
        self._playing = False
        for t in self._tracks.values():
            if t.player is not None:
                t.player.pause()

    def stop(self) -> None:
        self._playing = False
        for t in self._tracks.values():
            t.active_idx = -1
            if t.player is not None:
                t.player.stop()

    def seek(self, t_sec: float) -> None:
        self._last_t = float(t_sec)
        for t in self._tracks.values():
            if t.player is None:
                continue
            if t.schedule is not None:
                if t.enabled:
                    self._activate_scheduled(t, t_sec)
            else:
                t.player.setPosition(max(0, int(round(float(t_sec) * 1000))))

    def sync(self, t_sec: float) -> None:
        self._last_t = float(t_sec)
        for t in self._tracks.values():
            if not (t.enabled and t.player is not None):
                continue
            if t.schedule is not None:
                self._activate_scheduled(t, t_sec)
            elif t.path:
                cur = t.player.position() / 1000.0
                if self._should_resync(cur, t_sec):
                    t.player.setPosition(max(0, int(round(t_sec * 1000))))

    def _activate_scheduled(self, t: _Track, t_sec: float) -> None:
        """时间表轨：定位到 t_sec 对应的 clip 并播放（段间空隙暂停）。"""
        idx = self._active_clip_index(t.schedule, t_sec)
        if idx < 0:
            t.active_idx = -1
            t.player.pause()
            return
        t0, _t1, path = t.schedule[idx]
        offset_ms = max(0, int(round((t_sec - t0) * 1000)))
        if idx != t.active_idx:
            t.active_idx = idx
            t.player.setSource(QUrl.fromLocalFile(path))
            t.player.setPosition(offset_ms)
            if self._playing:
                t.player.play()
        else:
            cur = t.player.position() / 1000.0
            if self._should_resync(cur, t_sec - t0):
                t.player.setPosition(offset_ms)
            if self._playing:
                t.player.play()
