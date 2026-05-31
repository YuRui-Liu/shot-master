"""片段走马灯：缩略图卡（保留切换/选中）+ 卡间转场切口圆点。

对照 docs/explorer/成片合成-layout.html。封面缩略图由外部 set_thumb(clip_id, QPixmap)
注入（抽帧在 panel 的后台线程做），本控件只负责布局与交互信号。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QScrollArea, QFrame, QVBoxLayout, QLabel, QToolButton,
)


class _ClipCard(QFrame):
    def __init__(self, clip, on_click, on_keep):
        super().__init__()
        self.clip = clip
        self.setObjectName("ComposeClipCard")
        self.setFixedWidth(128)
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        self.thumb = QLabel(); self.thumb.setFixedHeight(152)
        self.thumb.setObjectName("ComposeClipThumb"); self.thumb.setAlignment(Qt.AlignCenter)
        self.keep_btn = QToolButton(self.thumb); self.keep_btn.setText("✓")
        self.keep_btn.setObjectName("ComposeKeepBtn"); self.keep_btn.move(6, 6)
        self.keep_btn.clicked.connect(lambda: on_keep(self.clip.clip_id))
        lay.addWidget(self.thumb)
        self.name = QLabel(clip.path.rsplit("/", 1)[-1]); self.name.setObjectName("ComposeClipName")
        lay.addWidget(self.name)
        self._on_click = on_click

    def mousePressEvent(self, e):
        self._on_click(self.clip.clip_id)
        super().mousePressEvent(e)

    def set_selected(self, on: bool):
        self.setProperty("selected", on); self.style().unpolish(self); self.style().polish(self)

    def set_dropped(self, on: bool):
        self.setProperty("dropped", on); self.style().unpolish(self); self.style().polish(self)

    def set_thumb(self, pixmap):
        self.thumb.setPixmap(pixmap)


class _Connector(QToolButton):
    def __init__(self, index, label, on_click):
        super().__init__()
        self.index = index
        self.setObjectName("ComposeConnector")
        self.setText(label)
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(lambda: on_click(self.index))

    def set_selected(self, on: bool):
        self.setProperty("selected", on); self.style().unpolish(self); self.style().polish(self)


class ClipStrip(QWidget):
    clipSelected = Signal(str)
    connectorSelected = Signal(int)
    keepToggled = Signal(str, bool)
    orderChanged = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = None
        self._cards: dict[str, _ClipCard] = {}
        self._connectors: list[_Connector] = []
        self._sel_clip = None
        self._sel_conn = None
        scroll = QScrollArea(self); scroll.setWidgetResizable(True)
        self._inner = QWidget(); self._row = QHBoxLayout(self._inner)
        self._row.setContentsMargins(4, 4, 4, 4); self._row.setSpacing(0)
        scroll.setWidget(self._inner)
        outer = QHBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.addWidget(scroll)

    def set_model(self, model):
        self._model = model
        self._rebuild()

    def _rebuild(self):
        while self._row.count():
            it = self._row.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self._cards.clear(); self._connectors.clear()
        if not self._model:
            return
        kept = self._model.kept_clips()
        clips = self._model.clips
        kept_index = {c.clip_id: i for i, c in enumerate(kept)}
        for c in clips:
            card = _ClipCard(c, self._emit_clip, self._emit_keep)
            card.set_dropped(not c.keep)
            self._cards[c.clip_id] = card
            self._row.addWidget(card)
            if c.keep and c.clip_id in kept_index and kept_index[c.clip_id] < len(kept) - 1:
                idx = kept_index[c.clip_id]
                conn = _Connector(idx, self._conn_label(kept[idx]), self._emit_conn)
                self._connectors.append(conn)
                self._row.addWidget(conn)
        self._row.addStretch(1)

    @staticmethod
    def _conn_label(clip) -> str:
        from drama_shot_master.core.transition_render import XFADE_EFFECTS
        name = clip.effective_transition()
        if name == "none":
            return "▭"
        label = next((e["label"] for e in XFADE_EFFECTS if e["name"] == name), name)
        return f"{label}\n{clip.effective_duration()}s"

    def select_clip(self, clip_id: str):
        self._set_sel_clip(clip_id); self.clipSelected.emit(clip_id)

    def select_connector(self, index: int):
        self._set_sel_conn(index); self.connectorSelected.emit(index)

    def toggle_keep(self, clip_id: str):
        if not self._model:
            return
        c = self._model.get(clip_id)
        if c is None:
            return
        c.keep = not c.keep
        self._rebuild()
        self.keepToggled.emit(clip_id, c.keep)

    def refresh(self):
        self._rebuild()

    def set_thumb(self, clip_id, pixmap):
        card = self._cards.get(clip_id)
        if card:
            card.set_thumb(pixmap)

    def _emit_clip(self, cid): self.select_clip(cid)
    def _emit_conn(self, idx): self.select_connector(idx)
    def _emit_keep(self, cid): self.toggle_keep(cid)

    def _set_sel_clip(self, cid):
        if self._sel_clip in self._cards:
            self._cards[self._sel_clip].set_selected(False)
        self._sel_clip = cid
        if cid in self._cards:
            self._cards[cid].set_selected(True)

    def _set_sel_conn(self, idx):
        for c in self._connectors:
            c.set_selected(c.index == idx)
        self._sel_conn = idx
