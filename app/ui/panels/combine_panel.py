"""拼图面板：order 模式选图 + R×C 拼接。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QVBoxLayout, QFormLayout, QGroupBox, QSpinBox, QComboBox,
    QLineEdit, QMessageBox,
)

from app.config import Config
from app.grid_ops import combine_to_file
from app.ui.panels.base_panel import BasePanel
from app.ui.state import AppState
from app.ui.worker import FunctionWorker


def _spin(lo, hi, val):
    s = QSpinBox(); s.setRange(lo, hi); s.setValue(val)
    return s


class CombinePanel(BasePanel):
    def __init__(self, state: AppState, cfg: Config, parent=None):
        super().__init__(state, cfg, parent)
        self._worker = None
        root = QVBoxLayout(self)

        box = QGroupBox("拼接参数")
        f = QFormLayout(box)
        self.t_rows = _spin(1, 50, 2)
        self.t_cols = _spin(1, 50, 2)
        self.gap = _spin(0, 999, 4)
        self.scale = QComboBox()
        self.scale.addItems(["letterbox", "crop", "stretch"])
        for w in (self.t_rows, self.t_cols):
            w.valueChanged.connect(self.validityChanged)
        f.addRow("目标 行", self.t_rows)
        f.addRow("目标 列", self.t_cols)
        f.addRow("间距", self.gap)
        f.addRow("缩放", self.scale)
        self.fmt = QComboBox(); self.fmt.addItems(["PNG", "JPG"])
        f.addRow("格式", self.fmt)
        self.out_name = QLineEdit("combined.png")
        f.addRow("输出文件名", self.out_name)
        root.addWidget(box)
        root.addStretch(1)

    def select_mode(self) -> str:
        return "order"

    def validate(self) -> tuple[bool, str]:
        if not self.state.output_dir:
            return False, "请先设置输出目录"
        need = self.t_rows.value() * self.t_cols.value()
        got = len(self.state.selected)
        if got != need:
            return False, f"需选 {need} 张·当前 {got} 张"
        return True, ""

    def execute(self):
        paths = self.state.selected_paths()
        out = self.state.output_dir / self.out_name.text().strip()
        tr, tc = self.t_rows.value(), self.t_cols.value()
        gap = self.gap.value()
        sm = self.scale.currentText()
        fmt = self.fmt.currentText()

        def task():
            combine_to_file(paths, out, target_rows=tr, target_cols=tc,
                            gap=gap, scale_mode=sm, output_format=fmt)
            return str(out)

        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(
            lambda s: QMessageBox.information(self, "完成", f"已生成 {s}"))
        self._worker.failed.connect(
            lambda e: QMessageBox.critical(self, "拼图失败", e))
        self._worker.start()
