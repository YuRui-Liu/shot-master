"""去白边面板：选中几张裁几张；不选=裁整目录。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QVBoxLayout, QFormLayout, QGroupBox, QSpinBox, QComboBox,
    QLineEdit, QMessageBox, QGridLayout, QWidget, QLabel,
)

from drama_shot_master.config import Config
from drama_shot_master.grid_ops import trim_one, trim_batch
from drama_shot_master.ui.panels.base_panel import BasePanel
from drama_shot_master.ui.state import AppState
from drama_shot_master.ui.worker import FunctionWorker


def _spin(lo, hi, val):
    s = QSpinBox(); s.setRange(lo, hi); s.setValue(val)
    return s


class TrimPanel(BasePanel):
    def __init__(self, state: AppState, cfg: Config, parent=None):
        super().__init__(state, cfg, parent)
        self._worker = None
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(13)
        box = QGroupBox("去白边参数")
        box.setObjectName("BatchGroup")
        f = QFormLayout(box)
        self.threshold = _spin(0, 255, 240)
        self.max_iter = _spin(1, 20, 5)
        self.suffix = QLineEdit("_trim")
        self.fmt = QComboBox(); self.fmt.addItems(["PNG", "JPG"])
        f.addRow("阈值", self.threshold)
        f.addRow("最大迭代", self.max_iter)
        f.addRow("命名后缀", self.suffix)
        f.addRow("格式", self.fmt)
        self.inset_top = _spin(0, 2000, 0)
        self.inset_bottom = _spin(0, 2000, 0)
        self.inset_left = _spin(0, 2000, 0)
        self.inset_right = _spin(0, 2000, 0)
        # 2×2 网格，每格 标签+spin；spin 给足宽度，避免数字被挤没
        inset_grid = QGridLayout()
        inset_grid.setContentsMargins(0, 0, 0, 0)
        inset_grid.setHorizontalSpacing(8)
        cells = (("上", self.inset_top, 0, 0), ("下", self.inset_bottom, 0, 2),
                 ("左", self.inset_left, 1, 0), ("右", self.inset_right, 1, 2))
        for lbl, sp, r, c in cells:
            sp.setMinimumWidth(72)
            inset_grid.addWidget(QLabel(lbl), r, c)
            inset_grid.addWidget(sp, r, c + 1)
        inset_grid.setColumnStretch(4, 1)
        inset_wrap = QWidget(); inset_wrap.setLayout(inset_grid)
        f.addRow("额外向内裁剪 (px)", inset_wrap)
        root.addWidget(box)
        root.addStretch(1)

    def select_mode(self) -> str:
        return "multi"

    def validate(self) -> tuple[bool, str]:
        if not self.state.output_dir:
            return False, "请先设置输出目录"
        if not self.state.current_dir and not self.state.selected:
            return False, "请先打开目录或选图"
        return True, ""

    def execute(self):
        out = self.state.output_dir
        th = self.threshold.value()
        mi = self.max_iter.value()
        suf = self.suffix.text()
        fmt = self.fmt.currentText()
        it = self.inset_top.value()
        ib = self.inset_bottom.value()
        il = self.inset_left.value()
        ir = self.inset_right.value()
        sel = self.state.selected_paths()
        src_dir = self.state.current_dir

        def task():
            if sel:
                ext = ".png" if fmt.upper() == "PNG" else ".jpg"
                for p in sel:
                    trim_one(p, out / f"{p.stem}{suf}{ext}",
                             threshold=th, max_iter=mi, output_format=fmt,
                             inset_top=it, inset_right=ir,
                             inset_bottom=ib, inset_left=il)
                return len(sel)
            files = trim_batch(src_dir, out, threshold=th, max_iter=mi,
                               output_format=fmt, name_suffix=suf,
                               inset_top=it, inset_right=ir,
                               inset_bottom=ib, inset_left=il)
            return len(files)

        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(
            lambda n: QMessageBox.information(self, "完成", f"已处理 {n} 张"))
        self._worker.failed.connect(
            lambda e: QMessageBox.critical(self, "去白边失败", e))
        self._worker.start()
