"""根据 Template 的 variables 动态生成补充输入表单。"""
from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QSpinBox, QDoubleSpinBox,
    QTextEdit, QComboBox, QLabel,
)


class TemplateFormWidget(QWidget):
    """暴露 get_values() 返回 {var_name: value} dict。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QFormLayout(self)
        self._inputs: dict[str, QWidget] = {}
        self._types: dict[str, str] = {}

    def set_variables(self, variables: list):
        """variables: list[TemplateVariable]"""
        # 清空旧
        while self._layout.rowCount() > 0:
            self._layout.removeRow(0)
        self._inputs = {}
        self._types = {}
        if not variables:
            self._layout.addRow(QLabel("（此模板无补充输入字段）"))
            return
        for v in variables:
            label = v.label + (" *" if v.required and not v.optional else "")
            widget = self._make_input(v)
            self._inputs[v.name] = widget
            self._types[v.name] = v.type
            self._layout.addRow(label, widget)

    def _make_input(self, v) -> QWidget:
        t = v.type
        if t == "int":
            w = QSpinBox()
            w.setRange(-1_000_000, 1_000_000)
            if isinstance(v.default, int):
                w.setValue(v.default)
            return w
        if t == "float":
            w = QDoubleSpinBox()
            w.setRange(-1e9, 1e9)
            w.setDecimals(3)
            if isinstance(v.default, (int, float)):
                w.setValue(float(v.default))
            return w
        if t == "select":
            w = QComboBox()
            w.addItems(v.options or [])
            if v.default is not None and str(v.default) in (v.options or []):
                w.setCurrentText(str(v.default))
            return w
        if t == "textarea":
            w = QTextEdit()
            w.setPlaceholderText(v.placeholder or "")
            w.setFixedHeight(90)
            if isinstance(v.default, str):
                w.setPlainText(v.default)
            return w
        # default: text
        w = QLineEdit()
        w.setPlaceholderText(v.placeholder or "")
        if isinstance(v.default, str):
            w.setText(v.default)
        return w

    def get_values(self) -> dict[str, Any]:
        out = {}
        for name, w in self._inputs.items():
            t = self._types.get(name, "text")
            if t == "int":
                out[name] = w.value()
            elif t == "float":
                out[name] = w.value()
            elif t == "select":
                out[name] = w.currentText()
            elif t == "textarea":
                out[name] = w.toPlainText()
            else:
                out[name] = w.text()
        return out
