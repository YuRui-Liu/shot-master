"""图片生成设置：provider / base_url / model / api_key / 输出目录。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QComboBox, QPushButton,
    QHBoxLayout, QFileDialog, QDialogButtonBox, QWidget, QLabel,
)

from drama_shot_master.config import Config

_PROVIDERS = [("豆包 (ARK)", "doubao"), ("OpenAI", "openai"),
              ("RunningHub (暂未接入)", "runninghub")]


class ImgGenSettingsDialog(QDialog):
    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("图片生成设置")
        self.setModal(True)
        self.resize(540, 300)
        root = QVBoxLayout(self)
        f = QFormLayout()
        self.provider = QComboBox()
        for label, key in _PROVIDERS:
            self.provider.addItem(label, key)
        cur = cfg.imggen_provider or "doubao"
        idx = next((i for i, (_l, k) in enumerate(_PROVIDERS) if k == cur), 0)
        self.provider.setCurrentIndex(idx)
        self.base_url = QLineEdit(cfg.imggen_base_url or "")
        self.model = QLineEdit(cfg.imggen_model or "")
        self.model.setPlaceholderText("如豆包 Seedream 模型 id")
        self.api_key = QLineEdit(cfg.imggen_api_key or (cfg.api_keys or {}).get(cur, ""))
        self.api_key.setEchoMode(QLineEdit.Password)
        self.out_dir = QLineEdit(cfg.imggen_output_dir or "")
        ob = QPushButton("选目录"); ob.clicked.connect(self._pick)
        orow = QHBoxLayout(); orow.addWidget(self.out_dir, 1); orow.addWidget(ob)
        ow = QWidget(); ow.setLayout(orow)
        f.addRow("提供方", self.provider)
        f.addRow("Base URL", self.base_url)
        f.addRow("模型 id", self.model)
        f.addRow("API Key", self.api_key)
        f.addRow("输出目录", ow)
        root.addLayout(f)
        root.addWidget(QLabel("RunningHub 图片工作流暂未接入。"))
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save); bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def _pick(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录", self.out_dir.text() or "")
        if d:
            self.out_dir.setText(d)

    def _save(self):
        prov = self.provider.currentData()
        self.cfg.update_settings(
            imggen_provider=prov, imggen_base_url=self.base_url.text().strip(),
            imggen_model=self.model.text().strip(),
            imggen_api_key=self.api_key.text().strip(),
            imggen_output_dir=self.out_dir.text().strip())
        self.accept()
