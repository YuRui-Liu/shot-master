"""灰色「上游缺失」条。

子面板在 set_project 之后自检上游产物缺失时显示；
位置统一在子面板的参数栏下、主编辑器上。
"""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel


class _UpstreamBanner(QFrame):
    """显示「上游缺失：请先在『阶段名』生成或手动放入 文件名」。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "QFrame { background: #3a3a2a; border: 1px solid #5a5a3a; }"
            "QLabel { color: #c0c0a0; padding: 6px; }")
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        self._label = QLabel("")
        h.addWidget(self._label)
        self.hide()

    def show_missing(self, stage_name: str, expected_file: str) -> None:
        self._label.setText(
            f"⚠ 上游缺失：请先在「{stage_name}」阶段生成，"
            f"或手动放入 {expected_file}")
        self.show()

    def hide_banner(self) -> None:
        self.hide()

    def text(self) -> str:
        return self._label.text()
