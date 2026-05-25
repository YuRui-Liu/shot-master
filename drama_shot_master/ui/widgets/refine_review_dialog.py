"""精炼结果逐行 review 弹窗：左原文右精炼，每行一个勾选框。"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QCheckBox,
    QPushButton, QScrollArea, QWidget, QFrame,
)


@dataclass
class RefineRow:
    key: str         # "global" 或 seg_id
    label: str       # "全局" / "段 N（image）"
    original: str
    refined: str


class RefineReviewDialog(QDialog):
    """构造入参 rows: list[RefineRow]；exec 后用 accepted_keys() 读勾选。"""

    def __init__(self, rows: list[RefineRow], parent=None):
        super().__init__(parent)
        self.setWindowTitle("提示词优化 · 逐行确认")
        self.setMinimumSize(720, 480)
        self._checks: dict[str, QCheckBox] = {}

        root = QVBoxLayout(self)
        # 顶部说明 + 全选/全不选
        top = QHBoxLayout()
        top.addWidget(QLabel("勾选要替换的项（左=原文，右=精炼）："))
        top.addStretch(1)
        btn_all = QPushButton("全部应用")
        btn_none = QPushButton("全部取消")
        btn_all.clicked.connect(lambda: self._set_all(True))
        btn_none.clicked.connect(lambda: self._set_all(False))
        top.addWidget(btn_all); top.addWidget(btn_none)
        root.addLayout(top)

        # 滚动区
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        inner = QWidget(); col = QVBoxLayout(inner)
        for r in rows:
            col.addWidget(self._build_row(r))
        col.addStretch(1)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        # 底部
        bottom = QHBoxLayout(); bottom.addStretch(1)
        ok = QPushButton("应用勾选"); cancel = QPushButton("取消")
        ok.clicked.connect(self.accept); cancel.clicked.connect(self.reject)
        bottom.addWidget(ok); bottom.addWidget(cancel)
        root.addLayout(bottom)

    def _build_row(self, r: RefineRow) -> QWidget:
        box = QFrame(); box.setFrameShape(QFrame.StyledPanel)
        v = QVBoxLayout(box)
        head = QHBoxLayout()
        cb = QCheckBox(r.label)
        # 精炼为空或与原文相同 → 默认不勾
        meaningful = bool(r.refined.strip()) and r.refined.strip() != r.original.strip()
        cb.setChecked(meaningful)
        cb.setEnabled(meaningful)
        self._checks[r.key] = cb
        head.addWidget(cb); head.addStretch(1)
        v.addLayout(head)
        cols = QHBoxLayout()
        left = QPlainTextEdit(r.original); left.setReadOnly(True)
        left.setMaximumHeight(90)
        right = QPlainTextEdit(r.refined); right.setReadOnly(True)
        right.setMaximumHeight(90)
        cols.addWidget(left); cols.addWidget(right)
        v.addLayout(cols)
        return box

    def _set_all(self, on: bool):
        for cb in self._checks.values():
            if cb.isEnabled():
                cb.setChecked(on)

    def accepted_keys(self) -> set[str]:
        return {k for k, cb in self._checks.items() if cb.isChecked()}
