"""编剧 Agent 配置 section（API key / base_url / 项目目录 / 4 阶段模型 / 模板说明）。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QPushButton, QLabel, QFileDialog,
    QHBoxLayout, QVBoxLayout, QFrame,
)


_STAGES = (("ideate", "创意"), ("script", "剧本"),
           ("storyboard", "分镜"), ("prompts", "提示词"))


class ScreenwriterSection(QWidget):
    title = "编剧"
    category = "生成功能"

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._build_ui()
        self.load_from(cfg)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        # —— 接入 LLM ——
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setContentsMargins(0, 0, 0, 0)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.api_key_edit = QLineEdit(); self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setMaximumWidth(480)
        self.base_url_edit = QLineEdit()
        self.base_url_edit.setMaximumWidth(480)
        self.base_url_edit.setPlaceholderText("如：https://api.deepseek.com")

        # 项目目录（浏览按钮）
        row = QHBoxLayout()
        self.project_root_edit = QLineEdit()
        self.project_root_edit.setPlaceholderText("空 = UI 内会提示选目录")
        btn_browse = QPushButton("浏览…"); btn_browse.clicked.connect(self._pick_root)
        row.addWidget(self.project_root_edit, 1); row.addWidget(btn_browse)
        proj_wrap = QWidget(); proj_wrap.setLayout(row)
        proj_wrap.setMaximumWidth(480)

        form.addRow("API Key", self.api_key_edit)
        form.addRow("Base URL", self.base_url_edit)
        form.addRow("项目目录", proj_wrap)
        root.addLayout(form)

        # —— 4 阶段模型 ——
        sep = QFrame(); sep.setFrameShape(QFrame.HLine); root.addWidget(sep)
        root.addWidget(QLabel("各阶段模型（可空，留空=用 Agent 内置默认）"))
        model_form = QFormLayout()
        model_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        model_form.setHorizontalSpacing(12); model_form.setVerticalSpacing(8)
        model_form.setContentsMargins(0, 0, 0, 0)
        self._model_edits: dict[str, QLineEdit] = {}
        for key, label in _STAGES:
            e = QLineEdit(); e.setMaximumWidth(480)
            self._model_edits[key] = e
            model_form.addRow(label, e)
        root.addLayout(model_form)

        # —— 提示词模板说明 ——
        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine); root.addWidget(sep2)
        tip = QLabel(
            "提示词模板：5 套内置（ideate/script/storyboard/character_ref/grid_prompt）。\n"
            "项目级覆盖位置：<项目目录>/.agent/templates/<id>.md（与同名内置模板同结构）。\n"
            "用户级编辑器留 P3（暂用文件管理器手工编辑覆盖文件）。")
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
        self.api_key_edit.setText(getattr(cfg, "screenwriter_llm_api_key", "") or "")
        self.base_url_edit.setText(getattr(cfg, "screenwriter_llm_base_url", "") or "")
        self.project_root_edit.setText(getattr(cfg, "screenwriter_project_root", "") or "")
        models = getattr(cfg, "screenwriter_models", None) or {}
        for key, _label in _STAGES:
            self._model_edits[key].setText(models.get(key, "") or "")

    def save_to(self, cfg):
        cfg.update_settings(
            screenwriter_llm_api_key=self.api_key_edit.text().strip(),
            screenwriter_llm_base_url=self.base_url_edit.text().strip(),
            screenwriter_project_root=self.project_root_edit.text().strip(),
            screenwriter_models={k: self._model_edits[k].text().strip()
                                 for k, _ in _STAGES
                                 if self._model_edits[k].text().strip()},
        )

    def validate(self):
        return (True, "")

    def cancel_workers(self):
        pass
