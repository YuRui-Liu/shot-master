"""配乐设置对话框：WorkflowID/默认输出目录/候选数/crossfade 等不常改项。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QFormLayout, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QSpinBox, QDoubleSpinBox, QWidget, QFileDialog, QDialogButtonBox,
)

from drama_shot_master.config import Config


class SoundtrackSettingsDialog(QDialog):
    """菜单栏「设置 → 配乐…」打开。"""

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("配乐设置")
        self.setModal(True)
        self.resize(520, 240)
        self._build_ui()
        self._load_from_cfg()

    def _build_ui(self):
        root = QVBoxLayout(self)
        form = QFormLayout()

        self.workflow_edit = QLineEdit()
        form.addRow("ACE-Step Workflow ID", self.workflow_edit)

        out_row = QHBoxLayout()
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("空=用 视频输出目录/soundtrack")
        b = QPushButton("浏览…"); b.clicked.connect(self._browse_out)
        out_row.addWidget(self.out_edit, 1); out_row.addWidget(b)
        out_wrap = QWidget(); out_wrap.setLayout(out_row)
        form.addRow("默认输出目录", out_wrap)

        self.seeds_spin = QSpinBox(); self.seeds_spin.setRange(1, 4)
        form.addRow("默认候选数", self.seeds_spin)

        self.crossfade_spin = QDoubleSpinBox()
        self.crossfade_spin.setRange(0.0, 3.0); self.crossfade_spin.setSingleStep(0.1)
        self.crossfade_spin.setDecimals(1); self.crossfade_spin.setSuffix(" s")
        form.addRow("crossfade 时长", self.crossfade_spin)

        root.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _load_from_cfg(self):
        self.workflow_edit.setText(
            getattr(self.cfg, "soundtrack_workflow_id", ""))
        self.out_edit.setText(getattr(self.cfg, "soundtrack_output_dir", ""))
        self.seeds_spin.setValue(
            int(getattr(self.cfg, "soundtrack_seeds_count", 2)))
        self.crossfade_spin.setValue(
            float(getattr(self.cfg, "soundtrack_crossfade", 0.5)))

    def _browse_out(self):
        d = QFileDialog.getExistingDirectory(
            self, "选择默认输出目录", self.out_edit.text() or "")
        if d:
            self.out_edit.setText(d)

    def accept(self):
        self.cfg.update_settings(
            soundtrack_workflow_id=self.workflow_edit.text().strip(),
            soundtrack_output_dir=self.out_edit.text().strip(),
            soundtrack_seeds_count=self.seeds_spin.value(),
            soundtrack_crossfade=self.crossfade_spin.value(),
        )
        super().accept()
