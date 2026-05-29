"""单个候选卡片：title + angle / summary / highlights 简略显示，点击可选定。"""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class _CandidateCard(QFrame):
    """候选卡片。点击 → emit clicked(id)。selected=True 时高亮边框。"""
    clicked = Signal(str)        # 候选 id

    def __init__(self, cand: dict, parent=None):
        super().__init__(parent)
        self._cid = cand.get("id", "")
        self._selected = False
        self.setObjectName("candidateCard")
        self.setFrameShape(QFrame.StyledPanel)
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 4, 6, 4); v.setSpacing(2)

        title = QLabel(f"<b>{cand.get('title', '(无标题)')}</b>")
        title.setTextFormat(Qt.RichText)
        v.addWidget(title)

        for key, label in (("angle", "切入角度"),
                            ("summary", "摘要"),
                            ("highlights", "看点")):
            text = (cand.get(key) or "").strip()
            if text:
                lab = QLabel(f"<span style='color:#9aa0a6'>{label}：</span>{text}")
                lab.setTextFormat(Qt.RichText)
                lab.setWordWrap(True)
                v.addWidget(lab)

    def candidate_id(self) -> str:
        return self._cid

    def set_selected(self, sel: bool) -> None:
        self._selected = sel
        self.setProperty("selected", "true" if sel else "false")
        # 重新应用 QSS（属性变化触发）
        self.style().unpolish(self); self.style().polish(self)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit(self._cid)
        super().mousePressEvent(ev)
