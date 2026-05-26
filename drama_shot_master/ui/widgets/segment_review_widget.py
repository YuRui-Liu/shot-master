"""②试听选优：每段候选试听 + 选定 + 重生成。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal, QUrl
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

from sound_track_agent import facade


class SegmentReviewWidget(QWidget):
    """按 session 渲染每段候选卡片。选定写 session、重生成发信号给任务窗。"""

    chosenChanged = Signal()
    regenerateRequested = Signal(int)

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self._session = session
        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)
        self._cards: list[dict] = []
        self._build_ui()

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
        outer.addWidget(scroll)

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
        self._cards.append({"buttons": buttons})
        return card

    def _on_candidate(self, seg_index: int, cand_index: int):
        seg = self._session.segments[seg_index]
        path = seg.candidates[cand_index].path
        if Path(path).exists():
            self._player.stop()
            self._player.setSource(QUrl.fromLocalFile(path))
            self._player.play()
        self.choose(seg_index, cand_index)

    def choose(self, seg_index: int, cand_index: int):
        facade.set_chosen(self._session, seg_index, cand_index)
        for ci, btn in enumerate(self._cards[seg_index]["buttons"]):
            btn.setChecked(ci == cand_index)
        self.chosenChanged.emit()

    def request_regenerate(self, seg_index: int):
        self.regenerateRequested.emit(seg_index)
