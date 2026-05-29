"""单行角色：name QLineEdit + appearance QLineEdit + [×]。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QPushButton


class _CharacterRow(QWidget):
    changed = Signal()       # 任何字段改动
    removeClicked = Signal(int)   # 自己被点删除

    def __init__(self, idx: int, name: str = "", appearance: str = "", parent=None):
        super().__init__(parent)
        self._idx = idx
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0); h.setSpacing(6)
        self.name_edit = QLineEdit(name)
        self.name_edit.setPlaceholderText("角色名")
        self.name_edit.setMaximumWidth(120)
        self.name_edit.textChanged.connect(self.changed)
        h.addWidget(self.name_edit)
        self.appearance_edit = QLineEdit(appearance)
        self.appearance_edit.setPlaceholderText("外貌（≥10 字）")
        self.appearance_edit.textChanged.connect(self.changed)
        h.addWidget(self.appearance_edit, 1)
        btn_del = QPushButton("×")
        btn_del.setMaximumWidth(28)
        btn_del.clicked.connect(lambda: self.removeClicked.emit(self._idx))
        h.addWidget(btn_del)

    def values(self) -> tuple[str, str]:
        return self.name_edit.text().strip(), self.appearance_edit.text().strip()
