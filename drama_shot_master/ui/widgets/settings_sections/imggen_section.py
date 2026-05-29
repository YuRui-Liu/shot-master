"""ImgGenSection：图片生成 provider 配置 section。"""
from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QComboBox, QPushButton,
    QHBoxLayout, QFileDialog, QLabel, QCheckBox,
)

from drama_shot_master.providers.image_gen import make_image_provider
from drama_shot_master.ui.theme import _tokens, current_theme, status_color
from drama_shot_master.ui.worker import FunctionWorker

_PROVIDERS = [("豆包 (ARK)", "doubao"), ("OpenAI", "openai"),
              ("RunningHub (暂未接入)", "runninghub")]


class ImgGenSection(QWidget):
    title = "出图"
    category = "生成功能"

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._worker: FunctionWorker | None = None
        self._build_ui()
        self.load_from(cfg)

    def _build_ui(self):
        root = QVBoxLayout(self)
        f = QFormLayout()

        self.provider = QComboBox()
        for label, key in _PROVIDERS:
            self.provider.addItem(label, key)
        f.addRow("提供方", self.provider)

        self.base_url = QLineEdit()
        f.addRow("Base URL", self.base_url)

        self.model = QLineEdit()
        self.model.setPlaceholderText("如豆包 Seedream 模型 id")
        f.addRow("模型 ID", self.model)

        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        f.addRow("API Key", self.api_key)

        out_row = QHBoxLayout()
        self.out_dir = QLineEdit()
        ob = QPushButton("选目录")
        ob.clicked.connect(self._pick)
        out_row.addWidget(self.out_dir, 1)
        out_row.addWidget(ob)
        ow = QWidget()
        ow.setLayout(out_row)
        f.addRow("输出目录", ow)

        self.no_watermark = QCheckBox("生成无水印图片")
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
        root.addStretch(1)

    def _pick(self):
        d = QFileDialog.getExistingDirectory(
            self, "选择输出目录", self.out_dir.text() or "")
        if d:
            self.out_dir.setText(d)

    def _current_provider(self):
        ns = SimpleNamespace(
            imggen_provider=self.provider.currentData(),
            imggen_api_key=self.api_key.text().strip(),
            api_keys=getattr(self._cfg, "api_keys", {}) or {},
            imggen_base_url=self.base_url.text().strip(),
            imggen_model=self.model.text().strip(),
            imggen_watermark=not self.no_watermark.isChecked(),
        )
        return make_image_provider(ns)

    def load_from(self, cfg):
        cur = getattr(cfg, "imggen_provider", None) or "doubao"
        idx = next((i for i, (_l, k) in enumerate(_PROVIDERS) if k == cur), 0)
        self.provider.setCurrentIndex(idx)
        self.base_url.setText(getattr(cfg, "imggen_base_url", "") or "")
        self.model.setText(getattr(cfg, "imggen_model", "") or "")
        api_key = getattr(cfg, "imggen_api_key", "") or (
            getattr(cfg, "api_keys", {}) or {}).get(cur, "")
        self.api_key.setText(api_key)
        self.out_dir.setText(getattr(cfg, "imggen_output_dir", "") or "")
        self.no_watermark.setChecked(
            not bool(getattr(cfg, "imggen_watermark", False)))

    def save_to(self, cfg):
        prov = self.provider.currentData()
        cfg.update_settings(
            imggen_provider=prov,
            imggen_base_url=self.base_url.text().strip(),
            imggen_model=self.model.text().strip(),
            imggen_api_key=self.api_key.text().strip(),
            imggen_output_dir=self.out_dir.text().strip(),
            imggen_watermark=not self.no_watermark.isChecked(),
        )

    def validate(self):
        return (True, "")

    def cancel_workers(self):
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(500)
            self._worker = None

    def _on_test(self):
        self.test_result.setText("测试中…")
        try:
            _t = _tokens(current_theme(self._cfg))
            self.test_result.setStyleSheet(f"color:{_t['fg_muted']};")
        except Exception:
            pass
        self.test_btn.setEnabled(False)
        provider = self._current_provider()

        def task():
            return provider.test_connection()

        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(self._on_test_done)
        self._worker.failed.connect(
            lambda e: self._on_test_done((False, f"内部错：{e}")))
        self._worker.start()

    def _on_test_done(self, res):
        ok, msg = res
        self.test_btn.setEnabled(True)
        self.test_result.setText(("✓ " if ok else "✗ ") + msg)
        try:
            _color = status_color("完成" if ok else "失败", self._cfg)
            self.test_result.setStyleSheet(f"color:{_color};")
        except Exception:
            pass
