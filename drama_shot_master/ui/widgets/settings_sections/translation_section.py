"""TranslationSection：DEEPLX_URL 配置 section。"""
from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QLabel,
)

from drama_shot_master.ui.theme import _tokens, current_theme


class TranslationSection(QWidget):
    title = "翻译"
    category = "平台核心"

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._build_ui()
        self.load_from(cfg)

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
        try:
            _t = _tokens(current_theme(self._cfg))
            tip.setStyleSheet(f"color:{_t['fg_muted']}")
        except Exception:
            pass
        root.addWidget(tip)
        root.addStretch(1)

    def load_from(self, cfg):
        self.url_edit.setText(getattr(cfg, "deeplx_url", "") or "")

    def save_to(self, cfg):
        url = self.url_edit.text().strip()
        cfg.update_settings(deeplx_url=url)
        if url:
            os.environ["DEEPLX_URL"] = url

    def validate(self):
        return (True, "")

    def cancel_workers(self):
        pass
