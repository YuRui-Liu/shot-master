"""RefineSection：提示词优化 provider 配置 section。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QComboBox, QPushButton,
    QLabel, QFileDialog, QHBoxLayout, QFrame,
)

from drama_shot_master.ui.worker import FunctionWorker

# 预设名 → (base_url, [model 建议])
_PRESETS = {
    "Ollama (本地)": ("http://localhost:11434/v1",
                      ["qwen2.5-vl", "qwen2.5-vl:7b", "qwen2.5-vl:32b"]),
    "豆包 ARK": ("https://ark.cn-beijing.volces.com/api/v3",
                 ["doubao-seed-1-6-vision-250815",
                  "doubao-1-5-vision-pro-32k-250115"]),
    "自定义": ("", []),
}


class RefineSection(QWidget):
    title = "提示词优化"
    category = "辅助"

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._worker: FunctionWorker | None = None
        self._build_ui()
        self.load_from(cfg)

    def _build_ui(self):
        root = QVBoxLayout(self)
        form = QFormLayout()

        self.preset_combo = QComboBox()
        self.preset_combo.addItems(list(_PRESETS.keys()))
        self.preset_combo.currentTextChanged.connect(self._on_preset_changed)
        form.addRow("Provider 预设", self.preset_combo)

        self.base_url_edit = QLineEdit()
        form.addRow("Base URL", self.base_url_edit)

        key_row = QHBoxLayout()
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.show_key_btn = QPushButton("👁")
        self.show_key_btn.setCheckable(True)
        self.show_key_btn.setMaximumWidth(40)
        self.show_key_btn.toggled.connect(
            lambda on: self.api_key_edit.setEchoMode(
                QLineEdit.Normal if on else QLineEdit.Password))
        key_row.addWidget(self.api_key_edit, 1)
        key_row.addWidget(self.show_key_btn)
        key_wrap = QWidget()
        key_wrap.setLayout(key_row)
        form.addRow("API Key", key_wrap)

        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        form.addRow("Model", self.model_combo)

        meta_row = QHBoxLayout()
        self.meta_edit = QLineEdit()
        self.meta_edit.setPlaceholderText(
            "留空 = 内置 templates/ltx_refine_meta_prompt.md")
        meta_browse = QPushButton("浏览…")
        meta_browse.clicked.connect(self._browse_meta)
        meta_row.addWidget(self.meta_edit, 1)
        meta_row.addWidget(meta_browse)
        meta_wrap = QWidget()
        meta_wrap.setLayout(meta_row)
        form.addRow("Meta-prompt 路径", meta_wrap)

        root.addLayout(form)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        root.addWidget(line)

        test_row = QHBoxLayout()
        self.test_btn = QPushButton("🔌 测试连接")
        self.test_btn.clicked.connect(self._on_test)
        self.test_label = QLabel("")
        self.test_label.setTextFormat(Qt.RichText)
        test_row.addWidget(self.test_btn)
        test_row.addWidget(self.test_label, 1)
        root.addLayout(test_row)
        root.addStretch(1)

    def _on_preset_changed(self, name: str):
        base_url, models = _PRESETS.get(name, ("", []))
        if base_url:
            self.base_url_edit.setText(base_url)
        cur = self.model_combo.currentText()
        self.model_combo.clear()
        self.model_combo.addItems(models)
        if cur:
            self.model_combo.setCurrentText(cur)

    def _browse_meta(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择 meta-prompt", "", "Markdown (*.md);;All (*)")
        if p:
            self.meta_edit.setText(p)

    def load_from(self, cfg):
        preset = getattr(cfg, "refine_provider_preset", None) or "Ollama (本地)"
        if preset in _PRESETS:
            self.preset_combo.setCurrentText(preset)
            self._on_preset_changed(preset)
        self.base_url_edit.setText(getattr(cfg, "refine_base_url", "") or "")
        self.api_key_edit.setText(getattr(cfg, "refine_api_key", "") or "")
        model = getattr(cfg, "refine_model", "") or ""
        if model:
            self.model_combo.setCurrentText(model)
        self.meta_edit.setText(getattr(cfg, "refine_meta_prompt_path", "") or "")

    def save_to(self, cfg):
        cfg.update_settings(
            refine_provider_preset=self.preset_combo.currentText(),
            refine_base_url=self.base_url_edit.text().strip(),
            refine_api_key=self.api_key_edit.text().strip(),
            refine_model=self.model_combo.currentText().strip(),
            refine_meta_prompt_path=self.meta_edit.text().strip(),
        )

    def validate(self):
        base_url = self.base_url_edit.text().strip()
        model = self.model_combo.currentText().strip()
        if not base_url or not model:
            return (False, "必须填 Base URL 和 Model")
        return (True, "")

    def cancel_workers(self):
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(500)
            self._worker = None

    def _on_test(self):
        base_url = self.base_url_edit.text().strip()
        model = self.model_combo.currentText().strip()
        api_key = self.api_key_edit.text().strip() or "ollama"
        if not base_url or not model:
            self.test_label.setText(
                '<span style="color:#f66">需先填 Base URL 和 Model</span>')
            return
        self.test_label.setText("测试中…")
        self.test_btn.setEnabled(False)

        def task():
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=base_url)
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
                timeout=20.0,
            )
            return resp.choices[0].message.content or "(空响应)"

        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(
            lambda _: self._test_done(True, "✓ 连接成功"))
        self._worker.failed.connect(
            lambda e: self._test_done(False, f"✗ {e}"))
        self._worker.start()

    def _test_done(self, ok: bool, msg: str):
        color = "#5fa" if ok else "#f66"
        self.test_label.setText(f'<span style="color:{color}">{msg}</span>')
        self.test_btn.setEnabled(True)
