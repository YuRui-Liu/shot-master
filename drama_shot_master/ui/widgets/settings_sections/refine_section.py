"""RefineSection：提示词优化（精简版）。

base_url + api_key 来自「平台核心 → LLM 平台」section；本 section 只
选 provider + 填 model + 选 meta-prompt 路径。
保存时把 refine_base_url / refine_api_key 从 LLM 平台映射写回 cfg，
下游 prompt_refiner.py 和 video_panel.py 不变。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QComboBox, QPushButton,
    QLabel, QFileDialog, QHBoxLayout, QFrame,
)

from .llm_platforms_section import PLATFORMS


# 默认 model 建议（按 provider id）
_DEFAULT_MODELS = {
    "deepseek": "deepseek-chat",
    "doubao":   "doubao-seed-1-6-vision-250815",
    "openai":   "gpt-4o-mini",
}


class RefineSection(QWidget):
    title = "提示词优化"
    category = "辅助"

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._build_ui()
        self.load_from(cfg)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 12, 20, 12)
        root.setSpacing(8)

        tip = QLabel("Provider 的 base_url / API Key 在「平台核心 → LLM 平台」统一配。")
        tip.setStyleSheet("color: #9aa0a6")
        root.addWidget(tip)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setHorizontalSpacing(12); form.setVerticalSpacing(8)
        form.setContentsMargins(0, 0, 0, 0)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        # provider 下拉
        self.provider_combo = QComboBox()
        for pid, plabel, _default_base in PLATFORMS:
            self.provider_combo.addItem(plabel, pid)
        self.provider_combo.setMaximumWidth(480)
        self.provider_combo.currentTextChanged.connect(self._on_provider_changed)
        form.addRow("Provider", self.provider_combo)

        self.model_edit = QLineEdit()
        self.model_edit.setMaximumWidth(480)
        self.model_edit.setPlaceholderText("model id（按所选 provider 填）")
        form.addRow("Model", self.model_edit)

        # Meta-prompt 路径（继承原行为）
        meta_row = QHBoxLayout()
        self.meta_edit = QLineEdit()
        self.meta_edit.setPlaceholderText(
            "留空 = 内置 templates/ltx_refine_meta_prompt.md")
        meta_browse = QPushButton("浏览…")
        meta_browse.clicked.connect(self._browse_meta)
        meta_row.addWidget(self.meta_edit, 1)
        meta_row.addWidget(meta_browse)
        meta_wrap = QWidget(); meta_wrap.setLayout(meta_row)
        meta_wrap.setMaximumWidth(480)
        form.addRow("Meta-prompt 路径", meta_wrap)

        root.addLayout(form)
        root.addStretch(1)

    def _on_provider_changed(self, _name: str):
        # 切 provider 时如果 model 为空，用默认建议填一个
        pid = self.provider_combo.currentData()
        if pid and not self.model_edit.text().strip():
            self.model_edit.setText(_DEFAULT_MODELS.get(pid, ""))

    def _browse_meta(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择 meta-prompt", "", "Markdown (*.md);;All (*)")
        if p:
            self.meta_edit.setText(p)

    def load_from(self, cfg):
        # 优先读新字段 refine_provider；没有就按旧 base_url 反查
        pid = getattr(cfg, "refine_provider", "") or self._guess_provider_from_url(
            getattr(cfg, "refine_base_url", "") or "")
        if not pid:
            pid = "deepseek"
        idx = self.provider_combo.findData(pid)
        self.provider_combo.setCurrentIndex(idx if idx >= 0 else 0)

        self.model_edit.setText(getattr(cfg, "refine_model", "") or "")
        self.meta_edit.setText(getattr(cfg, "refine_meta_prompt_path", "") or "")

    @staticmethod
    def _guess_provider_from_url(url: str) -> str:
        url = (url or "").lower()
        if "deepseek" in url:
            return "deepseek"
        if "volces" in url or "ark.cn" in url:
            return "doubao"
        if url:
            return "openai"
        return ""

    def save_to(self, cfg):
        pid = self.provider_combo.currentData() or "deepseek"
        # 从 LLM 平台拿 base_url + key（同步回扁平字段，下游不改）
        providers = getattr(cfg, "llm_providers", None) or {}
        provider_cfg = providers.get(pid) or {}
        # 默认 base_url 兜底（用户在 LLM 平台没填时，按 platform placeholder）
        default_base = next((b for p, _l, b in PLATFORMS if p == pid), "")
        cfg.update_settings(
            refine_provider=pid,
            refine_base_url=provider_cfg.get("base_url") or default_base,
            refine_api_key=provider_cfg.get("api_key", ""),
            refine_model=self.model_edit.text().strip(),
            refine_meta_prompt_path=self.meta_edit.text().strip(),
        )

    def validate(self):
        if not self.model_edit.text().strip():
            return (False, "Refine 的 Model 必填；base_url/key 在 LLM 平台配。")
        return (True, "")

    def cancel_workers(self):
        pass
