"""LLM 平台 section（统一 base_url + api_key + 测试连接）。

3 个平台（DeepSeek / 豆包·火山引擎 / 其它 OpenAI 兼容）各配一次。
其它功能（编剧等）按平台名引用，避免到处重填 key。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QPushButton, QLabel,
    QHBoxLayout, QVBoxLayout, QGroupBox,
)


# id → (显示名, 默认 base_url placeholder)
PLATFORMS = (
    ("deepseek", "DeepSeek",                "https://api.deepseek.com"),
    ("doubao",   "豆包·火山引擎",            "https://ark.cn-beijing.volces.com/api/v3"),
    ("openai",   "其它 OpenAI 兼容",         "https://api.openai.com/v1"),
)


class _PlatformBlock(QWidget):
    """单平台：base_url + api_key + [测试连接 + 测试 model]。"""

    def __init__(self, pid: str, label: str, default_base_url: str, parent=None):
        super().__init__(parent)
        self.pid = pid
        self._default_base_url = default_base_url
        self._build_ui(label)

    def _build_ui(self, label: str):
        box = QGroupBox(label)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(box)
        f = QFormLayout(box)
        f.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f.setHorizontalSpacing(12); f.setVerticalSpacing(8)
        f.setContentsMargins(10, 8, 10, 8)
        f.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.base_url_edit = QLineEdit()
        self.base_url_edit.setMaximumWidth(480)
        self.base_url_edit.setPlaceholderText(self._default_base_url)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setMaximumWidth(480)
        f.addRow("Base URL", self.base_url_edit)
        f.addRow("API Key", self.api_key_edit)

        # 测试行：[测试连接] [测试 model] 状态
        bar = QHBoxLayout()
        self.btn_test = QPushButton("测试连接")
        self.test_model_edit = QLineEdit()
        self.test_model_edit.setPlaceholderText("用什么 model 测试（必填）")
        self.test_model_edit.setMaximumWidth(240)
        self.lbl_status = QLabel("")
        bar.addWidget(self.btn_test)
        bar.addWidget(self.test_model_edit)
        bar.addWidget(self.lbl_status, 1)
        wrap = QWidget(); wrap.setLayout(bar)
        f.addRow("", wrap)
        self.btn_test.clicked.connect(self._on_test)

    def _on_test(self):
        self.lbl_status.setText("测试中…")
        self.lbl_status.setStyleSheet("color: #9aa0a6")
        self.lbl_status.repaint()
        base_url = self.base_url_edit.text().strip() or self._default_base_url
        api_key = self.api_key_edit.text().strip()
        model = self.test_model_edit.text().strip()
        if not api_key:
            self.lbl_status.setText("✗ 未填 API Key")
            self.lbl_status.setStyleSheet("color: #ff5c5c"); return
        if not model:
            self.lbl_status.setText("✗ 测试 model 必填")
            self.lbl_status.setStyleSheet("color: #ff5c5c"); return
        try:
            from openai import OpenAI
            c = OpenAI(api_key=api_key, base_url=base_url, timeout=15.0)
            r = c.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=4, stream=False)
            txt = (r.choices[0].message.content or "").strip()
            self.lbl_status.setText(f"✓ 通 · 回复 {len(txt)} 字符")
            self.lbl_status.setStyleSheet("color: #4ec98f")
        except Exception as e:
            self.lbl_status.setText(f"✗ {str(e)[:80]}")
            self.lbl_status.setStyleSheet("color: #ff5c5c")

    def load(self, base_url: str, api_key: str):
        self.base_url_edit.setText(base_url or "")
        self.api_key_edit.setText(api_key or "")

    def values(self) -> tuple[str, str]:
        return (self.base_url_edit.text().strip(),
                self.api_key_edit.text().strip())


class LLMPlatformsSection(QWidget):
    title = "LLM 平台"
    category = "平台核心"

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._blocks: dict[str, _PlatformBlock] = {}
        self._build_ui()
        self.load_from(cfg)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 12, 20, 12)
        root.setSpacing(8)
        intro = QLabel("各平台 base_url + key 在此处统一配；其它功能（编剧等）按平台名引用。")
        intro.setStyleSheet("color: #9aa0a6")
        root.addWidget(intro)
        for pid, label, default_base in PLATFORMS:
            blk = _PlatformBlock(pid, label, default_base)
            self._blocks[pid] = blk
            root.addWidget(blk)
        root.addStretch(1)

    def load_from(self, cfg):
        providers = getattr(cfg, "llm_providers", None) or {}
        # 向后兼容：旧 screenwriter_providers 字段
        legacy = getattr(cfg, "screenwriter_providers", None) or {}
        for pid, _label, _ in PLATFORMS:
            pc = providers.get(pid) or legacy.get(pid) or {}
            self._blocks[pid].load(pc.get("base_url", ""), pc.get("api_key", ""))

    def save_to(self, cfg):
        out = {}
        for pid, _label, _ in PLATFORMS:
            base, api = self._blocks[pid].values()
            if base or api:
                out[pid] = {"base_url": base, "api_key": api}
        cfg.update_settings(llm_providers=out)

    def validate(self):
        return (True, "")

    def cancel_workers(self):
        pass
