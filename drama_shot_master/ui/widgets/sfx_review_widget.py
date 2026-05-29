"""SFX 候选审阅：每个 SFXShot 一张卡片 + 底部共享试听播放器。

UI 与 SegmentReviewWidget 同构，绑 SFXSession.shots。
信号:
  chosenChanged          —— 用户切换候选时 emit
  regenerateRequested(i) —— 用户点 ↻ 重生成时 emit (shot_index)
  shotEdited             —— 用户改 prompt / duration / volume / enabled 时 emit
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal, QUrl, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSlider, QMessageBox, QLineEdit, QDoubleSpinBox, QCheckBox,
)


def _fmt(ms: int) -> str:
    s = max(0, ms) // 1000
    return f"{s // 60}:{s % 60:02d}"


class SfxReviewWidget(QWidget):
    chosenChanged = Signal()
    regenerateRequested = Signal(int)
    shotEdited = Signal()
    previewStarted = Signal()

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self._session = session
        self._player = None
        self._audio = None
        self._playing_key = None
        self._user_seeking = False
        self._cards: list[dict] = []
        self._build_ui()

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

    def shot_card_count(self) -> int:
        return len(self._cards)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        inner = QWidget(); col = QVBoxLayout(inner)
        for shot in self._session.shots:
            col.addWidget(self._make_card(shot))
        col.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

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

    def _make_card(self, shot) -> QWidget:
        card = QWidget()
        v = QVBoxLayout(card)
        v.addWidget(QLabel(
            f"镜 {shot.shot_index}  {shot.t_start:.1f}-{shot.t_end:.1f}s  "
            f"[{shot.status}]"))
        if shot.status == "skipped":
            v.addWidget(QLabel("LLM 判定该镜无需 SFX"))
            self._cards.append({"buttons": []})
            return card

        opt_row = QHBoxLayout()
        en = QCheckBox("启用")
        en.setChecked(shot.enabled)
        en.stateChanged.connect(
            lambda st, s=shot: self._on_enabled_changed(s, st == 2))
        opt_row.addWidget(en)
        opt_row.addWidget(QLabel("🔊"))
        vol = QDoubleSpinBox()
        vol.setRange(0.0, 1.5); vol.setSingleStep(0.05); vol.setDecimals(2)
        vol.setValue(float(shot.volume))
        vol.valueChanged.connect(
            lambda val, s=shot: self.set_volume(s.shot_index, val))
        opt_row.addWidget(vol)
        opt_row.addStretch(1)
        v.addLayout(opt_row)

        prompt_row = QHBoxLayout()
        prompt_row.addWidget(QLabel("描述"))
        edit = QLineEdit(shot.prompt_short)
        edit.editingFinished.connect(
            lambda e=edit, s=shot: self.set_prompt(s.shot_index, e.text()))
        prompt_row.addWidget(edit, 1)
        v.addLayout(prompt_row)

        dur_row = QHBoxLayout()
        dur_row.addWidget(QLabel("时长"))
        dur = QDoubleSpinBox()
        dur.setRange(1.0, 15.0); dur.setSingleStep(0.5); dur.setDecimals(1); dur.setSuffix(" s")
        dur.setValue(float(shot.duration))
        dur.valueChanged.connect(
            lambda val, s=shot: self._on_duration_changed(s, val))
        dur_row.addWidget(dur)
        dur_row.addStretch(1)
        v.addLayout(dur_row)

        cand_row = QHBoxLayout()
        buttons = []
        for ci, c in enumerate(shot.candidates):
            btn = QPushButton(f"▶ 候选{ci + 1}")
            btn.setCheckable(True)
            if shot.chosen_candidate == ci:
                btn.setChecked(True)
            btn.clicked.connect(
                lambda _c=False, si=shot.shot_index, c=ci: self._on_candidate(si, c))
            cand_row.addWidget(btn)
            buttons.append(btn)
        regen = QPushButton("↻ 重生成")
        regen.clicked.connect(
            lambda _c=False, si=shot.shot_index: self.request_regenerate(si))
        cand_row.addStretch(1); cand_row.addWidget(regen)
        v.addLayout(cand_row)

        self._cards.append({"buttons": buttons})
        return card

    def choose(self, shot_index: int, cand_index: int):
        shot = self._session.shots[shot_index]
        if 0 <= cand_index < len(shot.candidates):
            shot.chosen_candidate = cand_index
            for ci, btn in enumerate(self._cards[shot_index]["buttons"]):
                btn.setChecked(ci == cand_index)
            self.chosenChanged.emit()

    def request_regenerate(self, shot_index: int):
        self.regenerateRequested.emit(shot_index)

    def set_prompt(self, shot_index: int, prompt: str):
        self._session.shots[shot_index].prompt_short = str(prompt)
        self.shotEdited.emit()

    def set_volume(self, shot_index: int, vol: float):
        self._session.shots[shot_index].volume = float(vol)
        self.shotEdited.emit()
        if (self._player is not None and self._playing_key is not None
                and self._playing_key[0] == shot_index):
            self._audio.setVolume(min(1.0, max(0.0, float(vol))))

    def _on_enabled_changed(self, shot, enabled: bool):
        shot.enabled = enabled
        self.shotEdited.emit()

    def _on_duration_changed(self, shot, dur: float):
        shot.duration = max(1.0, min(15.0, float(dur)))
        self.shotEdited.emit()

    def _on_candidate(self, shot_index: int, cand_index: int):
        shot = self._session.shots[shot_index]
        path = shot.candidates[cand_index].path
        self.choose(shot_index, cand_index)
        if not Path(path).exists():
            QMessageBox.warning(self, "无法播放", f"候选文件缺失：{path}")
            return
        if self._playing_key == (shot_index, cand_index):
            self._toggle_play()
            return
        player = self._ensure_player()
        player.stop()
        player.setSource(QUrl.fromLocalFile(path))
        self._audio.setVolume(min(1.0, max(0.0, float(shot.volume))))
        self._playing_key = (shot_index, cand_index)
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
