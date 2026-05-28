"""编剧 Agent 配置 section（精简版）。

只剩 3 块：
  1. 项目目录
  2. 4 阶段映射（创意/剧本/分镜/提示词 → 平台下拉 + model 文本框）
  3. 提示词模板说明

平台的 base_url + api_key + 测试连接 在「平台核心 → LLM 平台」section 里统一配。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QPushButton, QLabel, QFileDialog,
    QHBoxLayout, QVBoxLayout, QFrame, QComboBox,
)


# 从 LLMPlatformsSection 引入平台清单，单一来源
from .llm_platforms_section import PLATFORMS


# 阶段 key → (显示名, 默认 provider, 默认 model)
_STAGES = (
    ("ideate",     "创意",     "doubao",   "doubao-1-5-thinking-pro-250415"),
    ("script",     "剧本",     "doubao",   "doubao-1-5-thinking-pro-250415"),
    ("storyboard", "分镜",     "deepseek", "deepseek-chat"),
    ("prompts",    "提示词",   "deepseek", "deepseek-chat"),
)


class ScreenwriterSection(QWidget):
    title = "编剧"
    category = "生成功能"

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._stage_widgets: dict[str, tuple[QComboBox, QLineEdit]] = {}
        self._build_ui()
        self.load_from(cfg)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 12, 20, 12)
        root.setSpacing(10)

        # —— 项目目录 ——
        ftop = QFormLayout()
        ftop.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        ftop.setHorizontalSpacing(12); ftop.setVerticalSpacing(8)
        ftop.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.project_root_edit = QLineEdit()
        self.project_root_edit.setPlaceholderText("空 = UI 内会提示选目录")
        btn_browse = QPushButton("浏览…"); btn_browse.clicked.connect(self._pick_root)
        row.addWidget(self.project_root_edit, 1); row.addWidget(btn_browse)
        proj_wrap = QWidget(); proj_wrap.setLayout(row)
        proj_wrap.setMaximumWidth(480)
        ftop.addRow("项目目录", proj_wrap)
        root.addLayout(ftop)

        # —— 提示信息 ——
        tip_link = QLabel(
            "平台的 base_url / API Key / 连通测试在「平台核心 → LLM 平台」统一配。")
        tip_link.setStyleSheet("color: #9aa0a6")
        root.addWidget(tip_link)

        # —— 阶段映射 ——
        sep = QFrame(); sep.setFrameShape(QFrame.HLine); root.addWidget(sep)
        root.addWidget(QLabel("各阶段用哪个平台 + model"))
        sform = QFormLayout()
        sform.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        sform.setHorizontalSpacing(12); sform.setVerticalSpacing(6)
        sform.setContentsMargins(0, 0, 0, 0)
        for skey, slabel, _default_pid, _default_model in _STAGES:
            combo = QComboBox()
            for pid, plabel, _ in PLATFORMS:
                combo.addItem(plabel, pid)
            model_edit = QLineEdit()
            model_edit.setPlaceholderText("model id（按所选平台填）")
            inner = QHBoxLayout()
            inner.addWidget(combo)
            inner.addWidget(model_edit, 1)
            wrap = QWidget(); wrap.setLayout(inner)
            wrap.setMaximumWidth(480)
            sform.addRow(slabel, wrap)
            self._stage_widgets[skey] = (combo, model_edit)
        root.addLayout(sform)

        # —— 模板说明 ——
        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine); root.addWidget(sep2)
        tip = QLabel(
            "提示词模板：5 套内置（ideate/script/storyboard/character_ref/grid_prompt）。\n"
            "项目级覆盖位置：<项目目录>/.agent/templates/<id>.md。")
        tip.setWordWrap(True); tip.setStyleSheet("color: #9aa0a6")
        root.addWidget(tip)
        root.addStretch(1)

    def _pick_root(self):
        d = QFileDialog.getExistingDirectory(
            self, "选编剧项目目录（每个子目录=一个项目）",
            self.project_root_edit.text() or "")
        if d:
            self.project_root_edit.setText(d)

    def load_from(self, cfg):
        self.project_root_edit.setText(
            getattr(cfg, "screenwriter_project_root", "") or "")
        assignments = getattr(cfg, "screenwriter_stage_assignments", None) or {}
        legacy_models = getattr(cfg, "screenwriter_models", None) or {}
        for skey, _slabel, default_pid, default_model in _STAGES:
            asn = assignments.get(skey) or {}
            pid = asn.get("provider", default_pid)
            model = asn.get("model", legacy_models.get(skey) or default_model)
            combo, model_edit = self._stage_widgets[skey]
            idx = combo.findData(pid)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            model_edit.setText(model)

    def save_to(self, cfg):
        assignments_out = {}
        for skey, _slabel, _default_pid, _default_model in _STAGES:
            combo, model_edit = self._stage_widgets[skey]
            assignments_out[skey] = {
                "provider": combo.currentData() or "",
                "model": model_edit.text().strip(),
            }
        cfg.update_settings(
            screenwriter_project_root=self.project_root_edit.text().strip(),
            screenwriter_stage_assignments=assignments_out,
        )

    def validate(self):
        return (True, "")

    def cancel_workers(self):
        pass
