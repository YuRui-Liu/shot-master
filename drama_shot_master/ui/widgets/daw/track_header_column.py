"""左侧轨道头控件列：原声/BGM/SFX 各一行 M/S/音量；对白只读占位。

行高/顺序与 DawTrackView 一致（垂直静态对齐）。
"""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
)

_AXIS_H = 14
_TRACK_H = {"video": 36, "bgm": 40, "sfx": 36, "dialogue": 36}
_TRACK_ORDER = ["video", "bgm", "sfx", "dialogue"]
_AUDIO_TRACKS = ["video", "bgm", "sfx"]
_GAP = 2
_NAMES = {"video": "原声", "bgm": "BGM", "sfx": "SFX", "dialogue": "对白"}

_MUTE_QSS = ("QPushButton{width:18px;border:1px solid #3d3d55;border-radius:3px;"
             "color:#a6adc8;font-size:10px;font-weight:700;}"
             "QPushButton:checked{background:#e05252;color:#fff;border-color:#e05252;}")
_SOLO_QSS = ("QPushButton{width:18px;border:1px solid #3d3d55;border-radius:3px;"
             "color:#a6adc8;font-size:10px;font-weight:700;}"
             "QPushButton:checked{background:#f9e2af;color:#1e1e2e;border-color:#f9e2af;}")


class TrackHeaderColumn(QWidget):
    muteToggled = Signal(str, bool)
    soloToggled = Signal(str, bool)
    volumeChanged = Signal(str, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(130)
        self._rows = {}
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(2, 0, 2, 0)
        root.setSpacing(_GAP)
        root.addSpacing(_AXIS_H)
        for track in _TRACK_ORDER:
            row = QWidget()
            row.setFixedHeight(_TRACK_H[track])
            hl = QHBoxLayout(row)
            hl.setContentsMargins(2, 1, 2, 1)
            hl.setSpacing(3)
            name = QLabel(_NAMES[track])
            name.setStyleSheet("font-size:11px;color:#cdd6f4;")
            name.setFixedWidth(30)
            hl.addWidget(name)
            if track in _AUDIO_TRACKS:
                mute = QPushButton("M"); mute.setCheckable(True)
                mute.setFixedWidth(20); mute.setStyleSheet(_MUTE_QSS)
                mute.clicked.connect(
                    lambda checked, t=track: self.muteToggled.emit(t, checked))
                solo = QPushButton("S"); solo.setCheckable(True)
                solo.setFixedWidth(20); solo.setStyleSheet(_SOLO_QSS)
                solo.clicked.connect(
                    lambda checked, t=track: self.soloToggled.emit(t, checked))
                vol = QSlider(Qt.Horizontal)
                vol.setRange(0, 150); vol.setValue(100)
                vol.valueChanged.connect(
                    lambda v, t=track: self.volumeChanged.emit(t, v / 100.0))
                hl.addWidget(mute); hl.addWidget(solo); hl.addWidget(vol, 1)
                self._rows[track] = {"mute": mute, "solo": solo, "vol": vol}
            else:
                ro = QLabel("（只读）")
                ro.setStyleSheet("font-size:9px;color:#6c7086;")
                hl.addWidget(ro); hl.addStretch(1)
            root.addWidget(row)
        root.addStretch(1)

    def set_state(self, mix) -> None:
        for track, ctl in self._rows.items():
            ctl["mute"].setChecked(mix.is_muted(track))
            ctl["solo"].setChecked(mix.is_soloed(track))
            ctl["vol"].blockSignals(True)
            ctl["vol"].setValue(int(round(mix.volume(track) * 100)))
            ctl["vol"].blockSignals(False)
