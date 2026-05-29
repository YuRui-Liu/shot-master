"""②试听选优：每段候选试听 + 选定 + 重生成。

播放器/音频输出懒创建（首次播放才建）：避免无音频环境（如 headless 测试）
构造时初始化音频后端导致卡顿/退出 segfault。底部共享一条 seek bar：点候选
即加载播放并显示可拖拽进度；再点同一候选切换 播放/暂停。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal, QUrl
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSlider, QMessageBox,
)
from PySide6.QtCore import Qt

from sound_track_agent import facade


def _fmt(ms: int) -> str:
    s = max(0, ms) // 1000
    return f"{s // 60}:{s % 60:02d}"


class SegmentReviewWidget(QWidget):
    """按 session 渲染每段候选卡片。选定写 session、重生成发信号给任务窗。"""

    chosenChanged = Signal()
    regenerateRequested = Signal(int)
    segmentVolumeChanged = Signal()
    previewStarted = Signal()

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self._session = session
        self._player = None              # 懒创建
        self._audio = None
        self._playing_key = None         # (seg_index, cand_index) 当前加载的候选
        self._user_seeking = False
        self._cards: list[dict] = []
        self._vol_sliders: list = []
        self._build_ui()

    # ---------- 懒创建播放器（首次播放才碰音频后端）----------
    def _ensure_player(self):
        if self._player is None:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            self._player = QMediaPlayer(self)
            self._audio = QAudioOutput(self)
            self._player.setAudioOutput(self._audio)
            self._player.positionChanged.connect(self._on_position)
            self._player.durationChanged.connect(self._on_duration)
            self._player.playbackStateChanged.connect(self._on_state)
        return self._player

    def segment_card_count(self) -> int:
        return len(self._cards)

    def all_chosen(self) -> bool:
        return all(s.chosen_candidate is not None
                   for s in self._session.segments)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        inner = QWidget(); col = QVBoxLayout(inner)
        for seg in self._session.segments:
            col.addWidget(self._make_card(seg))
        col.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        # 底部共享播放条（点候选后激活）
        bar = QHBoxLayout()
        self.play_btn = QPushButton("▶")
        self.play_btn.setMaximumWidth(40)
        self.play_btn.clicked.connect(self._toggle_play)
        self.seek = QSlider(Qt.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.sliderPressed.connect(lambda: setattr(self, "_user_seeking", True))
        self.seek.sliderReleased.connect(self._on_seek_released)
        self.time_label = QLabel("0:00 / 0:00")
        bar.addWidget(self.play_btn)
        bar.addWidget(self.seek, 1)
        bar.addWidget(self.time_label)
        outer.addLayout(bar)

    def _make_card(self, seg) -> QWidget:
        card = QWidget()
        v = QVBoxLayout(card)
        labels = ", ".join(seg.emotion.labels) if seg.emotion else ""
        v.addWidget(QLabel(f"段 {seg.index}  {seg.t_start:.1f}–{seg.t_end:.1f}s  {labels}"))
        row = QHBoxLayout()
        buttons = []
        for ci, cand in enumerate(seg.candidates):
            btn = QPushButton(f"▶ 候选{ci + 1}")
            btn.setCheckable(True)
            if seg.chosen_candidate == ci:
                btn.setChecked(True)
            btn.clicked.connect(
                lambda _c=False, si=seg.index, c=ci: self._on_candidate(si, c))
            row.addWidget(btn)
            buttons.append(btn)
        regen = QPushButton("↻ 重生成")
        regen.clicked.connect(lambda _c=False, si=seg.index: self.request_regenerate(si))
        row.addStretch(1); row.addWidget(regen)
        v.addLayout(row)
        vol_row = QHBoxLayout()
        vol_row.addWidget(QLabel("🔊 音量"))
        vslider = QSlider(Qt.Horizontal)
        vslider.setRange(0, 150)
        vslider.setValue(int(round(float(getattr(seg, "volume", 1.0)) * 100)))
        vlabel = QLabel(f"{vslider.value()}%")
        vslider.valueChanged.connect(
            lambda val, s=seg, lb=vlabel: self._on_volume(s, val, lb))
        vol_row.addWidget(vslider, 1); vol_row.addWidget(vlabel)
        v.addLayout(vol_row)
        self._vol_sliders.append(vslider)
        self._cards.append({"buttons": buttons})
        return card

    def _on_candidate(self, seg_index: int, cand_index: int):
        seg = self._session.segments[seg_index]
        path = seg.candidates[cand_index].path
        self.choose(seg_index, cand_index)        # 总是选定
        if not Path(path).exists():
            QMessageBox.warning(self, "无法播放", f"候选文件缺失：{path}")
            return
        if self._playing_key == (seg_index, cand_index):
            self._toggle_play()                   # 同一候选 → 切换 播放/暂停
            return
        player = self._ensure_player()
        player.stop()
        player.setSource(QUrl.fromLocalFile(path))
        # 开播前按当前 seg.volume 初始化一次
        self._audio.setVolume(
            min(1.0, max(0.0, float(getattr(seg, "volume", 1.0)))))
        self._playing_key = (seg_index, cand_index)
        self.previewStarted.emit()
        player.play()

    def _toggle_play(self):
        if self._player is None:
            return
        from PySide6.QtMultimedia import QMediaPlayer
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    # ---------- player 信号 → seek bar ----------
    def _on_position(self, ms: int):
        if not self._user_seeking:
            self.seek.setValue(ms)
        self.time_label.setText(f"{_fmt(ms)} / {_fmt(self.seek.maximum())}")

    def _on_duration(self, ms: int):
        self.seek.setRange(0, ms)

    def _on_state(self, _state):
        from PySide6.QtMultimedia import QMediaPlayer
        playing = (self._player is not None
                   and self._player.playbackState() == QMediaPlayer.PlayingState)
        self.play_btn.setText("⏸" if playing else "▶")

    def _on_seek_released(self):
        self._user_seeking = False
        if self._player is not None:
            self._player.setPosition(self.seek.value())

    def choose(self, seg_index: int, cand_index: int):
        facade.set_chosen(self._session, seg_index, cand_index)
        for ci, btn in enumerate(self._cards[seg_index]["buttons"]):
            btn.setChecked(ci == cand_index)
        self.chosenChanged.emit()

    def request_regenerate(self, seg_index: int):
        self.regenerateRequested.emit(seg_index)

    def _on_volume(self, seg, val: int, label):
        seg.volume = val / 100.0
        label.setText(f"{val}%")
        self.segmentVolumeChanged.emit()
        # 拖滑条时如果正在播这段的候选 → 立即更新 QAudioOutput
        if (self._player is not None and self._playing_key is not None
                and self._playing_key[0] == seg.index):
            self._audio.setVolume(min(1.0, max(0.0, float(seg.volume))))
