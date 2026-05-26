"""配音设置：两个 workflow_id + 输出目录 + 采样默认。节点号 profile 高级用户可在
 settings.json 的 dub_node_profiles 手改，这里不做复杂表单。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QPushButton, QHBoxLayout,
    QFileDialog, QDialogButtonBox, QLabel,
)

from drama_shot_master.config import Config


class DubSettingsDialog(QDialog):
    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("配音设置")
        self.setModal(True)
        self.resize(520, 280)
        root = QVBoxLayout(self)
        f = QFormLayout()
        ids = cfg.dub_workflow_ids or {}
        self.wf_design = QLineEdit(ids.get("voice_design", ""))
        self.wf_clone = QLineEdit(ids.get("voice_clone", ""))
        self.out_dir = QLineEdit(cfg.dub_output_dir or "")
        out_btn = QPushButton("选目录"); out_btn.clicked.connect(self._pick_dir)
        out_row = QHBoxLayout(); out_row.addWidget(self.out_dir, 1); out_row.addWidget(out_btn)
        from PySide6.QtWidgets import QWidget
        out_wrap = QWidget(); out_wrap.setLayout(out_row)
        f.addRow("音色设计 workflow_id", self.wf_design)
        f.addRow("声音克隆 workflow_id", self.wf_clone)
        f.addRow("输出目录", out_wrap)
        root.addLayout(f)
        root.addWidget(QLabel("高级：节点号映射可在 settings.json 的 dub_node_profiles 手改"))
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save); bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录", self.out_dir.text() or "")
        if d:
            self.out_dir.setText(d)

    def _save(self):
        self.cfg.update_settings(
            dub_workflow_ids={"voice_design": self.wf_design.text().strip(),
                              "voice_clone": self.wf_clone.text().strip()},
            dub_output_dir=self.out_dir.text().strip())
        self.accept()
