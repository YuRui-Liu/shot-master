"""ScreenwriterWizardHost：编剧面板右侧 wizard host。

顶部 stage stepper（N 按钮）+ QStackedWidget（N 子面板）。
stage 按钮无条件切换（spec issue #4），上游缺失由子面板自己显示 banner。
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QStackedWidget,
)


class ScreenwriterWizardHost(QWidget):
    """右侧 wizard host。"""
    stageChanged = Signal(int)

    def __init__(self, pages: list[QWidget], stage_names: list[str], parent=None):
        super().__init__(parent)
        assert len(pages) == len(stage_names)
        self._pages = pages
        self._buttons: list[QPushButton] = []
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 4, 4, 4); v.setSpacing(4)
        # Stage stepper
        bar = QHBoxLayout()
        bar.setSpacing(2)
        for i, name in enumerate(stage_names):
            btn = QPushButton(f"{i + 1}. {name}")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _checked, idx=i: self.set_stage(idx))
            bar.addWidget(btn)
            self._buttons.append(btn)
        bar.addStretch(1)
        v.addLayout(bar)
        # Stack
        self._stack = QStackedWidget()
        for pg in pages:
            self._stack.addWidget(pg)
        v.addWidget(self._stack, 1)
        self.set_stage(0)

    def set_stage(self, idx: int) -> None:
        n = self._stack.count()
        if idx < 0:
            idx = 0
        if idx >= n:
            idx = n - 1
        self._stack.setCurrentIndex(idx)
        for i, b in enumerate(self._buttons):
            b.setChecked(i == idx)
        self.stageChanged.emit(idx)
