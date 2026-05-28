"""编剧 Agent 配置 section。

每个阶段（创意/剧本/分镜/提示词）独立配 (base_url, api_key, model) —
因为豆包和 DeepSeek 是不同平台、不同 endpoint、不同 key。
每阶段一个「测试连接」按钮单独验。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QPushButton, QLabel, QFileDialog,
    QHBoxLayout, QVBoxLayout, QFrame, QGroupBox,
)


# 阶段 key → 显示名 + 默认 base_url
_STAGES = (
    ("ideate",     "创意",     "https://ark.cn-beijing.volces.com/api/v3"),
    ("script",     "剧本",     "https://ark.cn-beijing.volces.com/api/v3"),
    ("storyboard", "分镜",     "https://api.deepseek.com"),
    ("prompts",    "提示词",   "https://api.deepseek.com"),
)


class _StageBlock(QWidget):
    """单阶段配置块：base_url / api_key / model + 测试连接 + 状态文本。"""

    def __init__(self, key: str, label: str, default_base_url: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.label = label
        self._default_base_url = default_base_url
        self._build_ui()

    def _build_ui(self):
        box = QGroupBox(self.label)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(box)
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        form.setContentsMargins(10, 8, 10, 8)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.base_url_edit = QLineEdit()
        self.base_url_edit.setMaximumWidth(480)
        self.base_url_edit.setPlaceholderText(self._default_base_url)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setMaximumWidth(480)
        self.model_edit = QLineEdit()
        self.model_edit.setMaximumWidth(480)
        form.addRow("Base URL", self.base_url_edit)
        form.addRow("API Key", self.api_key_edit)
        form.addRow("Model", self.model_edit)

        # 测试连接行
        bar = QHBoxLayout()
        self.btn_test = QPushButton("测试连接")
        self.lbl_status = QLabel("")
        bar.addWidget(self.btn_test); bar.addWidget(self.lbl_status, 1)
        form.addRow("", self._wrap(bar))

        self.btn_test.clicked.connect(self._on_test)

    @staticmethod
    def _wrap(layout):
        w = QWidget(); w.setLayout(layout); return w

    def _on_test(self):
        """同步调一次 chat.completions.create(stream=False) 兜底测连通。
        失败/超时 → 红字；成功 → 绿字 + 模型名。"""
        self.lbl_status.setText("测试中…")
        self.lbl_status.setStyleSheet("color: #9aa0a6")
        self.lbl_status.repaint()
        base_url = (self.base_url_edit.text().strip()
                    or self._default_base_url)
        api_key = self.api_key_edit.text().strip()
        model = self.model_edit.text().strip()
        if not api_key:
            self.lbl_status.setText("✗ 未填 API Key")
            self.lbl_status.setStyleSheet("color: #ff5c5c")
            return
        if not model:
            self.lbl_status.setText("✗ 未填 Model")
            self.lbl_status.setStyleSheet("color: #ff5c5c")
            return
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=15.0)
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=4,
                stream=False)
            txt = (resp.choices[0].message.content or "").strip()
            self.lbl_status.setText(f"✓ 通 · 回复 {len(txt)} 字符")
            self.lbl_status.setStyleSheet("color: #4ec98f")
        except Exception as e:
            msg = str(e)[:80]
            self.lbl_status.setText(f"✗ {msg}")
            self.lbl_status.setStyleSheet("color: #ff5c5c")

    def load(self, base_url: str, api_key: str, model: str):
        self.base_url_edit.setText(base_url or "")
        self.api_key_edit.setText(api_key or "")
        self.model_edit.setText(model or "")

    def values(self) -> tuple[str, str, str]:
        return (self.base_url_edit.text().strip(),
                self.api_key_edit.text().strip(),
                self.model_edit.text().strip())


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

        # —— 项目目录 ——
        form_top = QFormLayout()
        form_top.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form_top.setHorizontalSpacing(12)
        form_top.setVerticalSpacing(10)
        form_top.setContentsMargins(0, 0, 0, 0)
        form_top.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        row = QHBoxLayout()
        self.project_root_edit = QLineEdit()
        self.project_root_edit.setPlaceholderText("空 = UI 内会提示选目录")
        btn_browse = QPushButton("浏览…"); btn_browse.clicked.connect(self._pick_root)
        row.addWidget(self.project_root_edit, 1); row.addWidget(btn_browse)
        proj_wrap = QWidget(); proj_wrap.setLayout(row)
        proj_wrap.setMaximumWidth(480)
        form_top.addRow("项目目录", proj_wrap)
        root.addLayout(form_top)

        # —— 4 个阶段独立配置 ——
        sep = QFrame(); sep.setFrameShape(QFrame.HLine); root.addWidget(sep)
        root.addWidget(QLabel("各阶段独立配置（不同平台需分别填 base_url 与 key）"))
        self._stages: dict[str, _StageBlock] = {}
        for key, label, default_base in _STAGES:
            blk = _StageBlock(key, label, default_base)
            self._stages[key] = blk
            root.addWidget(blk)

        # —— 提示词模板说明 ——
        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine); root.addWidget(sep2)
        tip = QLabel(
            "提示词模板：5 套内置（ideate/script/storyboard/character_ref/grid_prompt）。\n"
            "项目级覆盖位置：<项目目录>/.agent/templates/<id>.md（与同名内置模板同结构）。")
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
        # 每阶段配置存在 screenwriter_stage_configs dict：
        # {"ideate": {"base_url": "...", "api_key": "...", "model": "..."}}
        stages_cfg = getattr(cfg, "screenwriter_stage_configs", None) or {}
        # 向后兼容：旧扁平字段 → 全部阶段共用
        legacy_url = getattr(cfg, "screenwriter_llm_base_url", "") or ""
        legacy_key = getattr(cfg, "screenwriter_llm_api_key", "") or ""
        legacy_models = getattr(cfg, "screenwriter_models", None) or {}
        for key, _label, _ in _STAGES:
            sc = stages_cfg.get(key) or {}
            base = sc.get("base_url", legacy_url)
            api = sc.get("api_key", legacy_key)
            model = sc.get("model", legacy_models.get(key, ""))
            self._stages[key].load(base, api, model)

    def save_to(self, cfg):
        stage_cfgs = {}
        for key, _label, _ in _STAGES:
            base, api, model = self._stages[key].values()
            if base or api or model:
                stage_cfgs[key] = {"base_url": base, "api_key": api, "model": model}
        cfg.update_settings(
            screenwriter_project_root=self.project_root_edit.text().strip(),
            screenwriter_stage_configs=stage_cfgs,
        )

    def validate(self):
        return (True, "")

    def cancel_workers(self):
        pass
