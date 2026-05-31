"""画幅（输出比例）选择器：4 预设 + 自定义，可视分段控件。

立意页/项目设定用。值为 "W:H" 字符串（如 "16:9"）。默认 16:9。
记住上次由调用方负责（从 cfg 读 set_value、changed 时写 cfg）。
"""
from __future__ import annotations

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QToolButton, QButtonGroup, QLineEdit,
)

# (比例, 用途副标)；顺序即从左到右。
_PRESETS = [
    ("9:16", "竖屏·抖音"),
    ("16:9", "横屏·影视"),
    ("1:1", "方·社媒"),
    ("4:5", "竖·小红书"),
]
_PRESET_RATIOS = [r for r, _ in _PRESETS]
DEFAULT_RATIO = "16:9"

_RATIO_RE = re.compile(r"^\s*(\d{1,3})\s*[:：]\s*(\d{1,3})\s*$")


def parse_ratio(text: str) -> "str | None":
    """'16:9'/'16：9'（全角冒号）→ 规范化 'W:H'；非法 → None。"""
    m = _RATIO_RE.match(text or "")
    if not m:
        return None
    w, h = int(m.group(1)), int(m.group(2))
    if w <= 0 or h <= 0:
        return None
    return f"{w}:{h}"


class AspectRatioSelector(QWidget):
    """分段画幅选择器 + 自定义输入。value()->'W:H'；changed 发射当前值。"""

    changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = DEFAULT_RATIO
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._preset_btns: dict[str, QToolButton] = {}
        self._build()
        self.set_value(DEFAULT_RATIO)

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        for ratio, _sub in _PRESETS:
            btn = QToolButton()
            btn.setText(ratio)
            btn.setCheckable(True)
            btn.setToolTip(_sub)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, r=ratio: self._on_preset(r))
            self._group.addButton(btn)
            self._preset_btns[ratio] = btn
            lay.addWidget(btn)

        self._custom_btn = QToolButton()
        self._custom_btn.setText("自定义")
        self._custom_btn.setCheckable(True)
        self._custom_btn.setCursor(Qt.PointingHandCursor)
        self._custom_btn.clicked.connect(self._on_custom_clicked)
        self._group.addButton(self._custom_btn)
        lay.addWidget(self._custom_btn)

        self._custom_edit = QLineEdit()
        self._custom_edit.setPlaceholderText("W:H")
        self._custom_edit.setFixedWidth(64)
        self._custom_edit.setVisible(False)
        self._custom_edit.editingFinished.connect(self._on_custom_edit)
        lay.addWidget(self._custom_edit)
        lay.addStretch(1)

    # ── public ──────────────────────────────────────────────────────
    def value(self) -> str:
        return self._value

    def set_value(self, ratio: str) -> None:
        """设当前比例。预设→选中对应按钮；自定义比例→选「自定义」+ 填输入框。
        非法 → 退回默认。不发 changed（程序设值）。"""
        norm = parse_ratio(ratio) or DEFAULT_RATIO
        self._value = norm
        if norm in self._preset_btns:
            self._preset_btns[norm].setChecked(True)
            self._custom_edit.setVisible(False)
            self._custom_edit.clear()
        else:
            self._custom_btn.setChecked(True)
            self._custom_edit.setVisible(True)
            self._custom_edit.setText(norm)

    # ── internal ────────────────────────────────────────────────────
    def _on_preset(self, ratio: str):
        self._custom_edit.setVisible(False)
        self._set_and_emit(ratio)

    def _on_custom_clicked(self):
        self._custom_edit.setVisible(True)
        self._custom_edit.setFocus()
        cur = parse_ratio(self._custom_edit.text())
        if cur:
            self._set_and_emit(cur)

    def _on_custom_edit(self):
        norm = parse_ratio(self._custom_edit.text())
        if norm:
            self._custom_edit.setText(norm)
            self._set_and_emit(norm)

    def _set_and_emit(self, ratio: str):
        if ratio != self._value:
            self._value = ratio
            self.changed.emit(ratio)
