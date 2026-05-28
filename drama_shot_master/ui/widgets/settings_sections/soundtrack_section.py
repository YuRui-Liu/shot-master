"""SoundtrackSection：配乐 workflow_id / 输出目录 / 候选数 / crossfade 等配置 section。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QPushButton, QSpinBox,
    QDoubleSpinBox, QHBoxLayout, QFileDialog,
)


class SoundtrackSection(QWidget):
    title = "配乐"
    category = "生成功能"

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._build_ui()
        self.load_from(cfg)

    def _build_ui(self):
        root = QVBoxLayout(self)
        form = QFormLayout()

        self.workflow_edit = QLineEdit()
        form.addRow("ACE-Step Workflow ID", self.workflow_edit)

        out_row = QHBoxLayout()
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("空=用 视频输出目录/soundtrack")
        b = QPushButton("浏览…")
        b.clicked.connect(self._browse_out)
        out_row.addWidget(self.out_edit, 1)
        out_row.addWidget(b)
        out_wrap = QWidget()
        out_wrap.setLayout(out_row)
        form.addRow("默认输出目录", out_wrap)

        self.seeds_spin = QSpinBox()
        self.seeds_spin.setRange(1, 4)
        form.addRow("默认候选数", self.seeds_spin)

        self.crossfade_spin = QDoubleSpinBox()
        self.crossfade_spin.setRange(0.0, 3.0)
        self.crossfade_spin.setSingleStep(0.1)
        self.crossfade_spin.setDecimals(1)
        self.crossfade_spin.setSuffix(" s")
        form.addRow("crossfade 时长", self.crossfade_spin)

        self.big_thresh_spin = QDoubleSpinBox()
        self.big_thresh_spin.setRange(0.0, 1.0)
        self.big_thresh_spin.setSingleStep(0.05)
        self.big_thresh_spin.setDecimals(2)
        form.addRow("大卡点强度阈值", self.big_thresh_spin)

        self.snap_window_spin = QDoubleSpinBox()
        self.snap_window_spin.setRange(0.0, 3.0)
        self.snap_window_spin.setSingleStep(0.1)
        self.snap_window_spin.setDecimals(1)
        self.snap_window_spin.setSuffix(" s")
        form.addRow("段切吸附窗口", self.snap_window_spin)

        root.addLayout(form)
        root.addStretch(1)

    def _browse_out(self):
        d = QFileDialog.getExistingDirectory(
            self, "选择默认输出目录", self.out_edit.text() or "")
        if d:
            self.out_edit.setText(d)

    def load_from(self, cfg):
        self.workflow_edit.setText(
            getattr(cfg, "soundtrack_workflow_id", "") or "")
        self.out_edit.setText(
            getattr(cfg, "soundtrack_output_dir", "") or "")
        self.seeds_spin.setValue(
            int(getattr(cfg, "soundtrack_seeds_count", 2)))
        self.crossfade_spin.setValue(
            float(getattr(cfg, "soundtrack_crossfade", 0.5)))
        self.big_thresh_spin.setValue(
            float(getattr(cfg, "accent_big_threshold", 0.7)))
        self.snap_window_spin.setValue(
            float(getattr(cfg, "accent_snap_window", 0.6)))

    def save_to(self, cfg):
        cfg.update_settings(
            soundtrack_workflow_id=self.workflow_edit.text().strip(),
            soundtrack_output_dir=self.out_edit.text().strip(),
            soundtrack_seeds_count=self.seeds_spin.value(),
            soundtrack_crossfade=self.crossfade_spin.value(),
            accent_big_threshold=self.big_thresh_spin.value(),
            accent_snap_window=self.snap_window_spin.value(),
        )

    def validate(self):
        return (True, "")

    def cancel_workers(self):
        pass
