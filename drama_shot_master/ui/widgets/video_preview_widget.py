"""视频预览 widget：QVideoWidget + 工具栏 + 节流 seek。

封装 QMediaPlayer 让上层只看到 set_source/seek/play/pause/duration/is_playing 6 个
方法 + 1 个 positionChanged(float) signal。

Player 懒创建（避免 headless 测试 segfault），首次 set_source 才碰音视频后端。
"""
from __future__ import annotations
from pathlib import Path

from PySide6.QtCore import Signal, QUrl, QTimer, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSlider,
)


class VideoPreviewWidget(QWidget):
    positionChanged = Signal(float)   # 秒
    playingChanged = Signal(bool)     # 播放/暂停状态变化
    _SEEK_THROTTLE_MS = 33            # ~30Hz

    def __init__(self, parent=None):
        super().__init__(parent)
        self._player = None
        self._audio = None
        self._video_widget = None
        self._duration_sec = 0.0
        self._loaded_source = None
        self._pending_volume = None
        self._pending_muted = None
        self._pending_seek_ms = None
        self._seek_timer = QTimer(self)
        self._seek_timer.setSingleShot(True)
        self._seek_timer.setInterval(self._SEEK_THROTTLE_MS)
        self._seek_timer.timeout.connect(self._flush_seek)
        self._build_ui()

    def _build_ui(self):
        from PySide6.QtMultimediaWidgets import QVideoWidget
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self._video_widget = QVideoWidget(self)
        self._video_widget.setMinimumHeight(180)
        self._video_widget.setStyleSheet("background:#000;")
        root.addWidget(self._video_widget, 1)
        bar = QHBoxLayout()
        self.btn_play = QPushButton("▶")
        self.btn_play.setMaximumWidth(40)
        self.btn_play.clicked.connect(self._toggle_play)
        self.time_label = QLabel("0:00 / 0:00")
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 150)
        self.vol_slider.setValue(80)
        self.vol_slider.setMaximumWidth(120)
        self.vol_slider.valueChanged.connect(self._on_volume)
        bar.addWidget(self.btn_play)
        bar.addWidget(self.time_label)
        bar.addStretch(1)
        bar.addWidget(QLabel("🔊"))
        bar.addWidget(self.vol_slider)
        root.addLayout(bar)

    def _ensure_player(self):
        if self._player is None:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            self._player = QMediaPlayer(self)
            self._audio = QAudioOutput(self)
            self._player.setAudioOutput(self._audio)
            self._player.setVideoOutput(self._video_widget)
            self._player.positionChanged.connect(self._on_position_changed)
            self._player.durationChanged.connect(self._on_duration_changed)
            self._player.playbackStateChanged.connect(self._on_state_changed)
            self._audio.setVolume(self.vol_slider.value() / 100.0)
            if self._pending_volume is not None:
                self._audio.setVolume(self._pending_volume)
            if self._pending_muted is not None:
                self._audio.setMuted(self._pending_muted)
        return self._player

    def set_source(self, video_path) -> None:
        """加载 mp4；None / 空 / 不存在 → 仅 stop，不加载（黑屏）。

        同源重复调用直接返回，避免 stop() 把正在播放的视频跳回 0:00 并暂停
        （切播放模式时所有模式共用同一原片，不应打断）。"""
        if not video_path or not Path(str(video_path)).exists():
            if self._player is not None:
                self._player.stop()
            self._loaded_source = None
            return
        s = str(video_path)
        if s == self._loaded_source and self._player is not None:
            return
        player = self._ensure_player()
        player.stop()
        player.setSource(QUrl.fromLocalFile(s))
        self._loaded_source = s

    def seek(self, t_sec: float) -> None:
        if self._player is None:
            return
        self._pending_seek_ms = max(0, int(round(float(t_sec) * 1000)))
        if not self._seek_timer.isActive():
            self._seek_timer.start()

    def _flush_seek(self):
        if self._player is None or self._pending_seek_ms is None:
            return
        self._player.setPosition(self._pending_seek_ms)
        self._pending_seek_ms = None

    def play(self) -> None:
        if self._player is not None:
            self._player.play()

    def pause(self) -> None:
        if self._player is not None:
            self._player.pause()

    def is_playing(self) -> bool:
        if self._player is None:
            return False
        from PySide6.QtMultimedia import QMediaPlayer
        return self._player.playbackState() == QMediaPlayer.PlayingState

    def duration(self) -> float:
        return self._duration_sec

    def set_volume(self, v: float) -> None:
        """设原声音量 0–1.5。player 未建则记录，建后应用。"""
        v = max(0.0, min(1.5, float(v)))
        self._pending_volume = v
        if self._audio is not None:
            self._audio.setVolume(v)

    def set_muted(self, on: bool) -> None:
        self._pending_muted = bool(on)
        if self._audio is not None:
            self._audio.setMuted(bool(on))

    def position(self) -> float:
        """当前播放位置（秒）。无 player → 0.0。"""
        if self._player is None:
            return 0.0
        return self._player.position() / 1000.0

    def _toggle_play(self):
        if self._player is None:
            return
        if self.is_playing():
            self._player.pause()
        else:
            self._player.play()

    def _on_position_changed(self, ms: int):
        t = ms / 1000.0
        self.positionChanged.emit(t)
        self._update_time_label(t)

    def _on_duration_changed(self, ms: int):
        self._duration_sec = ms / 1000.0
        self._update_time_label(0.0)

    def _on_state_changed(self, _state):
        playing = self.is_playing()
        self.btn_play.setText("⏸" if playing else "▶")
        self.playingChanged.emit(playing)

    def _on_volume(self, val: int):
        if self._audio is not None:
            self._audio.setVolume(val / 100.0)

    def _update_time_label(self, t_sec: float):
        def _fmt(s: float) -> str:
            s = max(0, int(s))
            return f"{s // 60}:{s % 60:02d}"
        self.time_label.setText(f"{_fmt(t_sec)} / {_fmt(self._duration_sec)}")
