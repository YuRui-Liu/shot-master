"""TranslationSettingsDialog：菜单栏「设置 → 翻译配置…」打开。"""
from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QLabel, QDialogButtonBox,
)

from drama_shot_master.config import Config


class TranslationSettingsDialog(QDialog):
    """配 DEEPLX_URL（用于 prompt 中文预览）。"""

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("翻译配置")
        self.setModal(True)
        self.resize(520, 180)
        self._build_ui()
        self._load_from_cfg()

    def _build_ui(self):
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText(
            "https://api.deeplx.org/translate（留空则用 .env 的 DEEPLX_URL）")
        form.addRow("DeepLX URL", self.url_edit)
        root.addLayout(form)
        tip = QLabel("公共实例可能不稳定，可改为自部署 "
                     "http://localhost:1188/translate。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#888")
        root.addWidget(tip)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _load_from_cfg(self):
        self.url_edit.setText(self.cfg.deeplx_url)

    def accept(self):
        url = self.url_edit.text().strip()
        self.cfg.update_settings(deeplx_url=url)
        if url:
            os.environ["DEEPLX_URL"] = url
        super().accept()
