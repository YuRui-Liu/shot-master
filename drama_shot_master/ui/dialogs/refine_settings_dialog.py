"""RefineSettingsDialog：菜单栏「设置 → 提示词优化配置…」打开。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QPushButton, QLabel, QFileDialog, QWidget, QDialogButtonBox, QFrame,
    QMessageBox,
)

from drama_shot_master.config import Config
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


class RefineSettingsDialog(QDialog):
    """配 meta-prompt 路径 + 反推专用 provider（base_url/key/model）。"""

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._worker: FunctionWorker | None = None
        self.setWindowTitle("提示词优化配置")
        self.setModal(True)
        self.resize(560, 360)
        self._build_ui()
        self._load_from_cfg()

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
        key_wrap = QWidget(); key_wrap.setLayout(key_row)
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
        meta_wrap = QWidget(); meta_wrap.setLayout(meta_row)
        form.addRow("Meta-prompt 路径", meta_wrap)

        root.addLayout(form)

        line = QFrame(); line.setFrameShape(QFrame.HLine)
        root.addWidget(line)

        test_row = QHBoxLayout()
        self.test_btn = QPushButton("🔌 测试连接")
        self.test_btn.clicked.connect(self._on_test)
        self.test_label = QLabel("")
        self.test_label.setTextFormat(Qt.RichText)
        test_row.addWidget(self.test_btn)
        test_row.addWidget(self.test_label, 1)
        root.addLayout(test_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

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

    def _load_from_cfg(self):
        preset = self.cfg.refine_provider_preset or "Ollama (本地)"
        if preset in _PRESETS:
            self.preset_combo.setCurrentText(preset)
            self._on_preset_changed(preset)
        self.base_url_edit.setText(self.cfg.refine_base_url)
        self.api_key_edit.setText(self.cfg.refine_api_key)
        if self.cfg.refine_model:
            self.model_combo.setCurrentText(self.cfg.refine_model)
        self.meta_edit.setText(self.cfg.refine_meta_prompt_path)

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

    def accept(self):
        base_url = self.base_url_edit.text().strip()
        model = self.model_combo.currentText().strip()
        if not base_url or not model:
            QMessageBox.warning(self, "校验失败", "必须填 Base URL 和 Model")
            return
        self.cfg.update_settings(
            refine_provider_preset=self.preset_combo.currentText(),
            refine_base_url=base_url,
            refine_api_key=self.api_key_edit.text().strip(),
            refine_model=model,
            refine_meta_prompt_path=self.meta_edit.text().strip(),
        )
        super().accept()
