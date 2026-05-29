"""编剧 Agent 配置 section（精简版）。

只剩 3 块：
  1. 项目目录
  2. 4 阶段映射（创意/剧本/分镜/提示词 → 平台下拉 + model 文本框）
  3. 提示词模板编辑（QToolBox，global override）

平台的 base_url + api_key + 测试连接 在「平台核心 → LLM 平台」section 里统一配。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QPushButton, QLabel, QFileDialog,
    QHBoxLayout, QVBoxLayout, QFrame, QComboBox, QToolBox, QPlainTextEdit,
)


# 从 LLMPlatformsSection 引入平台清单，单一来源
from .llm_platforms_section import PLATFORMS

from screenwriter_agent.templates import template_loader as tl


# 阶段 key → (显示名, 默认 provider, 默认 model)
# 默认用 DeepSeek 当前主推的 V4 模型（见 deepseek.com 官方定价页）。
_STAGES = (
    ("ideate",     "创意",     "deepseek", "deepseek-v4-flash"),
    ("script",     "剧本",     "deepseek", "deepseek-v4-flash"),
    ("storyboard", "分镜",     "deepseek", "deepseek-v4-flash"),
    ("prompts",    "提示词",   "deepseek", "deepseek-v4-flash"),
)

# QToolBox 页：(页标题, [(tid, 编辑器标签或 None)])
# None 标签 = 该页只有一个 editor，不额外显示小标签
_TEMPLATE_PAGES = (
    ("创意",   [("ideate",        None)]),
    ("剧本",   [("script",        None)]),
    ("分镜",   [("storyboard",    None)]),
    ("提示词", [("character_ref", "角色参考图模板（character_ref）"),
                ("grid_prompt",   "N 宫格模板（grid_prompt）")]),
)


def _make_editor_with_buttons(tid: str) -> tuple[QWidget, QPlainTextEdit, QLabel]:
    """返回 (container, editor, hint_label)。

    container 包含：hint_label + 工具栏（重置 + 打开文件） + editor。
    """
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 4, 0, 0)
    layout.setSpacing(4)

    # hint label（灰色，source != global 时显示）
    hint = QLabel()
    hint.setStyleSheet("color: #9aa0a6; font-size: 11px;")
    hint.setVisible(False)
    layout.addWidget(hint)

    # 工具栏行（右对齐）
    toolbar = QHBoxLayout()
    toolbar.setContentsMargins(0, 0, 0, 0)
    toolbar.addStretch(1)

    btn_reset = QPushButton("重置到默认")
    btn_reset.setFixedHeight(22)
    btn_reset.setToolTip("清除全局覆盖文件，回退到内置默认")

    btn_open = QPushButton("打开全局模板文件")
    btn_open.setFixedHeight(22)
    btn_open.setToolTip("用系统编辑器打开全局覆盖文件")

    toolbar.addWidget(btn_reset)
    toolbar.addWidget(btn_open)
    layout.addLayout(toolbar)

    # 编辑器
    editor = QPlainTextEdit()
    editor.setMinimumHeight(220)
    layout.addWidget(editor)

    # 重置按钮行为：删除 global 文件 → reload → 重填
    def _on_reset():
        tl.write_global_template(tid, "")          # 删除 global 文件
        new_text, new_src = tl.load_template(tid)  # project_dir=None
        editor.setPlainText(new_text)
        editor._original_text = new_text           # 重置原始记录
        _update_hint(new_src)

    # 打开文件按钮：确保文件存在再打开（若不存在则写空字符串-实际是不会创建，改为先创建）
    def _on_open():
        p = tl.global_template_path(tid)
        if not p.is_file():
            # 先把当前编辑器内容写过去
            tl.write_global_template(tid, editor.toPlainText())
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))

    btn_reset.clicked.connect(_on_reset)
    btn_open.clicked.connect(_on_open)

    # hint 文字辅助函数
    def _update_hint(source: str):
        if source != "global":
            hint.setText("当前显示：内置默认（你还没改过）")
            hint.setVisible(True)
        else:
            hint.setVisible(False)

    # 存在 container 上，方便外部调用
    container._update_hint = _update_hint  # type: ignore[attr-defined]

    return container, editor, hint


class ScreenwriterSection(QWidget):
    title = "编剧"
    category = "生成功能"

    def __init__(self, cfg=None, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._stage_widgets: dict[str, tuple[QComboBox, QLineEdit]] = {}
        # tid -> QPlainTextEdit
        self._template_editors: dict[str, QPlainTextEdit] = {}
        # tid -> container（持有 _update_hint）
        self._template_containers: dict[str, QWidget] = {}
        self._build_ui()
        if cfg is not None:
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

        # —— 提示词模板 ——
        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine); root.addWidget(sep2)

        tmpl_header = QLabel(
            "编辑后保存即生效全局默认；项目目录 .agent/templates/ 仍可覆盖全局。")
        tmpl_header.setWordWrap(True)
        tmpl_header.setStyleSheet("color: #9aa0a6")
        root.addWidget(tmpl_header)

        toolbox = QToolBox()
        root.addWidget(toolbox)

        for page_title, editors_spec in _TEMPLATE_PAGES:
            page_widget = QWidget()
            page_layout = QVBoxLayout(page_widget)
            page_layout.setContentsMargins(4, 4, 4, 4)
            page_layout.setSpacing(6)

            for tid, sub_label in editors_spec:
                if sub_label is not None:
                    lbl = QLabel(sub_label)
                    lbl.setStyleSheet("font-weight: bold;")
                    page_layout.addWidget(lbl)

                container, editor, _hint = _make_editor_with_buttons(tid)
                page_layout.addWidget(container)

                # 初始化 _original_text 占位（load_from 时会覆盖）
                editor._original_text = ""  # type: ignore[attr-defined]
                self._template_editors[tid] = editor
                self._template_containers[tid] = container

            page_layout.addStretch(1)
            toolbox.addItem(page_widget, page_title)

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

        # 加载模板内容
        for tid, editor in self._template_editors.items():
            text, source = tl.load_template(tid)  # project_dir=None → skip project
            editor.setPlainText(text)
            editor._original_text = text  # type: ignore[attr-defined]
            container = self._template_containers[tid]
            if hasattr(container, "_update_hint"):
                container._update_hint(source)  # type: ignore[attr-defined]

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

        # 保存模板覆盖（只写改动过的）
        for tid, editor in self._template_editors.items():
            current_text = editor.toPlainText()
            original = getattr(editor, "_original_text", None)
            if current_text != original:
                tl.write_global_template(tid, current_text)

    def validate(self):
        return (True, "")

    def cancel_workers(self):
        pass
