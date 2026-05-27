"""图片生成设置：provider / base_url / model / api_key / 输出目录 / 无水印 + 连通测试。"""
from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QComboBox, QPushButton,
    QHBoxLayout, QFileDialog, QDialogButtonBox, QWidget, QLabel, QCheckBox,
)

from drama_shot_master.config import Config
from drama_shot_master.providers.image_gen import make_image_provider
from drama_shot_master.ui.worker import FunctionWorker

_PROVIDERS = [("豆包 (ARK)", "doubao"), ("OpenAI", "openai"),
              ("RunningHub (暂未接入)", "runninghub")]


class ImgGenSettingsDialog(QDialog):
    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._worker = None
        self.setWindowTitle("图片生成设置")
        self.setModal(True)
        self.resize(560, 340)
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
        self.no_watermark = QCheckBox("生成无水印图片")
        self.no_watermark.setChecked(not bool(cfg.imggen_watermark))
        f.addRow("提供方", self.provider)
        f.addRow("Base URL", self.base_url)
        f.addRow("模型 id", self.model)
        f.addRow("API Key", self.api_key)
        f.addRow("输出目录", ow)
        f.addRow("", self.no_watermark)
        root.addLayout(f)

        # 连通测试
        test_row = QHBoxLayout()
        self.test_btn = QPushButton("🔌 测试连接")
        self.test_btn.clicked.connect(self._on_test)
        self.test_result = QLabel("")
        test_row.addWidget(self.test_btn)
        test_row.addWidget(self.test_result, 1)
        root.addLayout(test_row)

        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save); bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def _pick(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录", self.out_dir.text() or "")
        if d:
            self.out_dir.setText(d)

    def _current_provider(self):
        ns = SimpleNamespace(
            imggen_provider=self.provider.currentData(),
            imggen_api_key=self.api_key.text().strip(),
            api_keys=self.cfg.api_keys or {},
            imggen_base_url=self.base_url.text().strip(),
            imggen_model=self.model.text().strip(),
            imggen_watermark=not self.no_watermark.isChecked(),
        )
        return make_image_provider(ns)

    def _on_test(self):
        self.test_result.setText("测试中…")
        self.test_result.setStyleSheet("color:#888;")
        self.test_btn.setEnabled(False)
        provider = self._current_provider()

        def task():
            return provider.test_connection()

        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(self._on_test_done)
        self._worker.failed.connect(lambda e: self._on_test_done((False, f"内部错：{e}")))
        self._worker.start()

    def _on_test_done(self, res):
        ok, msg = res
        self.test_btn.setEnabled(True)
        self.test_result.setText(("✓ " if ok else "✗ ") + msg)
        self.test_result.setStyleSheet("color:#2BAA4A;" if ok else "color:#D9544D;")

    def _save(self):
        prov = self.provider.currentData()
        self.cfg.update_settings(
            imggen_provider=prov, imggen_base_url=self.base_url.text().strip(),
            imggen_model=self.model.text().strip(),
            imggen_api_key=self.api_key.text().strip(),
            imggen_output_dir=self.out_dir.text().strip(),
            imggen_watermark=not self.no_watermark.isChecked())
        self.accept()
