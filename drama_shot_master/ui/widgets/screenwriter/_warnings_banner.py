"""自适应高度的 warnings 红条。点击单条 → emit warningClicked(path)。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel


_SEV_COLOR = {
    "info":     "#9aa0a6",
    "warning":  "#ffaa00",
    "error":    "#ff5c5c",
    "critical": "#ff3a3a",
}


class _WarningsBanner(QFrame):
    warningClicked = Signal(str)        # path 字段

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(6, 4, 6, 4); self._layout.setSpacing(2)
        self._items: list[QLabel] = []
        self.hide()

    def set_warnings(self, warns: list[dict]) -> None:
        # 清空
        for lab in self._items:
            lab.deleteLater()
        self._items = []
        if not warns:
            self.hide()
            return
        self.show()
        for w in warns[:10]:
            sev = w.get("severity", "warning")
            color = _SEV_COLOR.get(sev, "#9aa0a6")
            path = w.get("path", "")
            issue = w.get("issue", "")
            lab = QLabel(
                f"<a href='{path}' style='color:{color}; text-decoration:none'>"
                f"⚠ {path}</a> · <span style='color:#9aa0a6'>{issue}</span>")
            lab.setTextFormat(Qt.RichText)
            lab.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
            lab.linkActivated.connect(self._emit_click)
            self._layout.addWidget(lab)
            self._items.append(lab)

    def _emit_click(self, path: str):
        self.warningClicked.emit(path)
