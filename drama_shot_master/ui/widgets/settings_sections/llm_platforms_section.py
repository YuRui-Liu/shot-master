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
        v = QVBoxLayout(box)
        v.setContentsMargins(10, 8, 10, 8); v.setSpacing(6)
        f = QFormLayout()
        f.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f.setHorizontalSpacing(12); f.setVerticalSpacing(8)
        f.setContentsMargins(0, 0, 0, 0)
        f.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.base_url_edit = QLineEdit()
        self.base_url_edit.setMaximumWidth(480)
        self.base_url_edit.setPlaceholderText(self._default_base_url)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setMaximumWidth(480)
        f.addRow("Base URL", self.base_url_edit)
        f.addRow("API Key", self.api_key_edit)
        v.addLayout(f)

        # 测试行
        test_bar = QHBoxLayout()
        self.btn_test = QPushButton("测试连接")
        test_bar.addWidget(self.btn_test); test_bar.addStretch(1)
        v.addLayout(test_bar)
        # 状态独占下一行 —— 定高单行 + 省略号截断 + 全文挂 tooltip，
        # 保证报错再长也不会撑变形上下挤压上面的输入框
        self.lbl_status = QLabel("")
        self.lbl_status.setFixedHeight(20)
        self.lbl_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_status.setTextFormat(Qt.PlainText)
        # ElideRight 由 QLabel 单行自动截断；用 setStyleSheet 配 white-space:nowrap 难，
        # 改用 fontMetrics 手动截字以保证视觉一致
        v.addWidget(self.lbl_status)

        self.btn_test.clicked.connect(self._on_test)

    # 每个平台测试策略不同（ARK 的 /models 不通用，要 chat.completions）
    _ARK_FALLBACK_MODEL = "doubao-1-5-pro-32k-241215"

    def _on_test(self):
        self._set_status("测试中…", "#9aa0a6")
        base_url = self.base_url_edit.text().strip() or self._default_base_url
        api_key = self.api_key_edit.text().strip()
        if not api_key:
            self._set_status("✗ 未填 API Key", "#ff5c5c"); return
        try:
            from openai import OpenAI
            c = OpenAI(api_key=api_key, base_url=base_url, timeout=15.0)
            if self.pid == "doubao":
                # ARK 的 /v3/models 不可用，用 chat.completions 兜底；
                # 用一个公开 model 名做 ping（用户没开通会失败，但鉴权层会先通过）
                resp = c.chat.completions.create(
                    model=self._ARK_FALLBACK_MODEL,
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=4, stream=False)
                _txt = (resp.choices[0].message.content or "").strip()
                self._set_status(
                    f"✓ 鉴权通过 · 测试 model: {self._ARK_FALLBACK_MODEL}",
                    "#4ec98f")
            else:
                # DeepSeek / OpenAI 都支持 /models 列表
                models = c.models.list()
                ids = [m.id for m in (models.data or [])][:5]
                preview = "、".join(ids) if ids else "（无可见 model）"
                self._set_status(f"✓ 鉴权通过 · 可见 model: {preview}", "#4ec98f")
        except Exception as e:
            msg = str(e)
            self._set_status(f"✗ {msg}", "#ff5c5c", tooltip=msg)

    def _set_status(self, text: str, color: str, tooltip: str = ""):
        """单行截断（按当前字体宽度算）+ 全文挂 tooltip，定高不撑变形。"""
        fm = self.lbl_status.fontMetrics()
        # 留出 8px 边距
        avail = max(80, self.lbl_status.width() - 8)
        elided = fm.elidedText(text, Qt.ElideRight, avail)
        self.lbl_status.setText(elided)
        self.lbl_status.setToolTip(tooltip or text)
        self.lbl_status.setStyleSheet(f"color: {color}")

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
