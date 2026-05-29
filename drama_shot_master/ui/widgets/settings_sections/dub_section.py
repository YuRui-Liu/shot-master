"""DubSection：配音 workflow_ids / 输出目录 配置 section。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QPushButton, QHBoxLayout,
    QFileDialog, QLabel,
)


class DubSection(QWidget):
    title = "配音"
    category = "生成功能"

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._build_ui()
        self.load_from(cfg)

    def _build_ui(self):
        root = QVBoxLayout(self)
        f = QFormLayout()

        self.wf_design = QLineEdit()
        f.addRow("音色设计 ID", self.wf_design)

        self.wf_clone = QLineEdit()
        f.addRow("声音克隆 ID", self.wf_clone)

        out_row = QHBoxLayout()
        self.out_dir = QLineEdit()
        out_btn = QPushButton("选目录")
        out_btn.clicked.connect(self._pick_dir)
        out_row.addWidget(self.out_dir, 1)
        out_row.addWidget(out_btn)
        out_wrap = QWidget()
        out_wrap.setLayout(out_row)
        f.addRow("输出目录", out_wrap)

        root.addLayout(f)
        root.addWidget(
            QLabel("高级：节点号映射可在 settings.json 的 dub_node_profiles 手改"))
        root.addStretch(1)

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(
            self, "选择输出目录", self.out_dir.text() or "")
        if d:
            self.out_dir.setText(d)

    def load_from(self, cfg):
        ids = getattr(cfg, "dub_workflow_ids", None) or {}
        self.wf_design.setText(ids.get("voice_design", ""))
        self.wf_clone.setText(ids.get("voice_clone", ""))
        self.out_dir.setText(getattr(cfg, "dub_output_dir", "") or "")

    def save_to(self, cfg):
        cfg.update_settings(
            dub_workflow_ids={
                "voice_design": self.wf_design.text().strip(),
                "voice_clone": self.wf_clone.text().strip(),
            },
            dub_output_dir=self.out_dir.text().strip(),
        )

    def validate(self):
        return (True, "")

    def cancel_workers(self):
        pass
