"""DAW 工具栏: 播放 / zoom / 撤销 / 配置 + 信号。"""
from __future__ import annotations
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel, QSlider,
)


class DawToolbar(QWidget):
    playPauseRequested = Signal()
    zoomInRequested = Signal()
    zoomOutRequested = Signal()
    zoomChanged = Signal(float)      # 0.0-1.0 slider value
    fitRequested = Signal()
    undoRequested = Signal()
    redoRequested = Signal()
    configRequested = Signal()

    def __init__(self, undo_stack, parent=None):
        super().__init__(parent)
        self._undo_stack = undo_stack
        self._build_ui()
        undo_stack.canUndoChanged.connect(self.btn_undo.setEnabled)
        undo_stack.canRedoChanged.connect(self.btn_redo.setEnabled)
        self.btn_undo.setEnabled(undo_stack.can_undo())
        self.btn_redo.setEnabled(undo_stack.can_redo())

    def _build_ui(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        self.btn_play = QPushButton("▶")
        self.btn_play.setMaximumWidth(32)
        self.btn_play.clicked.connect(self.playPauseRequested.emit)
        self.time_label = QLabel("0:00 / 0:00")
        self.btn_zoom_out = QPushButton("-")
        self.btn_zoom_out.setMaximumWidth(28)
        self.btn_zoom_out.clicked.connect(self.zoomOutRequested.emit)
        self.btn_zoom_in = QPushButton("+")
        self.btn_zoom_in.setMaximumWidth(28)
        self.btn_zoom_in.clicked.connect(self.zoomInRequested.emit)
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(0, 100)
        self.zoom_slider.setValue(0)
        self.zoom_slider.setMaximumWidth(180)
        self.zoom_slider.valueChanged.connect(
            lambda v: self.zoomChanged.emit(v / 100.0))
        self.btn_fit = QPushButton("FIT")
        self.btn_fit.setMaximumWidth(40)
        self.btn_fit.clicked.connect(self.fitRequested.emit)
        self.btn_undo = QPushButton("↶")
        self.btn_undo.setMaximumWidth(32)
        self.btn_undo.clicked.connect(self.undoRequested.emit)
        self.btn_redo = QPushButton("↷")
        self.btn_redo.setMaximumWidth(32)
        self.btn_redo.clicked.connect(self.redoRequested.emit)
        self.btn_config = QPushButton("⚙")
        self.btn_config.setMaximumWidth(32)
        self.btn_config.clicked.connect(self.configRequested.emit)
        for w in (self.btn_play, self.time_label,
                  QLabel("zoom"), self.btn_zoom_out, self.zoom_slider,
                  self.btn_zoom_in, self.btn_fit,
                  self.btn_undo, self.btn_redo):
            lay.addWidget(w)
        lay.addStretch(1)
        lay.addWidget(self.btn_config)

    def set_time(self, current_sec: float, total_sec: float):
        def _fmt(s):
            s = max(0, int(s))
            return f"{s // 60}:{s % 60:02d}"
        self.time_label.setText(f"{_fmt(current_sec)} / {_fmt(total_sec)}")

    def set_playing(self, playing: bool):
        self.btn_play.setText("⏸" if playing else "▶")
