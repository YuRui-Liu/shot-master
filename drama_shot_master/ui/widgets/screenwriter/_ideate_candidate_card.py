"""单个候选卡片：title + angle / summary / highlights 显示，点击可选定。

可视风格自带 stylesheet（不依赖外部 QSS）：
- 圆角 + 浅蓝色描边
- hover 高亮
- selected 状态用更深蓝边框 + 浅蓝背景
"""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


_CARD_QSS = """
QFrame#candidateCard {
    background: #2a2d31;
    border: 1px solid #3a3d42;
    border-radius: 8px;
    padding: 4px;
}
QFrame#candidateCard:hover {
    background: #2f3338;
    border: 1px solid #5a5d62;
}
QFrame#candidateCard[selected="true"] {
    background: #1e3a4e;
    border: 2px solid #4a9eff;
}
QFrame#candidateCard QLabel {
    background: transparent;
    color: #e0e0e0;
}
QFrame#candidateCard QLabel#cardTitle {
    color: #ffffff;
    font-size: 12pt;
    font-weight: bold;
}
"""


class _CandidateCard(QFrame):
    """候选卡片。点击 → emit clicked(id)。selected=True 时高亮边框 + 浅蓝底。"""
    clicked = Signal(str)        # 候选 id

    def __init__(self, cand: dict, parent=None):
        super().__init__(parent)
        self._cid = cand.get("id", "")
        self._selected = False
        self.setObjectName("candidateCard")
        self.setFrameShape(QFrame.StyledPanel)
        self.setProperty("selected", "false")
        # 内嵌 stylesheet（不依赖应用层 QSS——保证主题没载入时也看起来像卡片）
        self.setStyleSheet(_CARD_QSS)
        # 让属性变化触发 :hover/[selected] QSS 重新计算
        self.setAttribute(Qt.WA_StyledBackground, True)
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 8, 10, 8); v.setSpacing(4)

        title = QLabel(cand.get("title", "(无标题)"))
        title.setObjectName("cardTitle")
        title.setWordWrap(True)
        v.addWidget(title)

        for key, label in (("angle", "切入角度"),
                            ("summary", "摘要"),
                            ("highlights", "看点")):
            text = (cand.get(key) or "").strip()
            if text:
                row = QLabel(
                    f"<span style='color:#8a9099; font-size:9pt'>{label}：</span>"
                    f"<span style='color:#d0d0d0'>{text}</span>")
                row.setTextFormat(Qt.RichText)
                row.setWordWrap(True)
                v.addWidget(row)

    def candidate_id(self) -> str:
        return self._cid

    def set_selected(self, sel: bool) -> None:
        self._selected = sel
        self.setProperty("selected", "true" if sel else "false")
        # 重新应用 QSS（属性变化必须 unpolish/polish 才能命中 [selected] 选择器）
        self.style().unpolish(self); self.style().polish(self)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit(self._cid)
        super().mousePressEvent(ev)
