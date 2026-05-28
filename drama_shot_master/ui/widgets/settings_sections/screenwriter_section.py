"""编剧 Agent 配置 section。

布局：
  - 项目目录
  - LLM 平台（3 个：DeepSeek / 豆包·火山引擎 / 其它 OpenAI 兼容）
    每个平台 base_url + api_key + [测试连接]，全 section 仅 3 次测试
  - 4 阶段「使用哪个平台 + model」（下拉选 provider + 文本框填 model）

避免每阶段重复填同一组 key——共用平台共享配置。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QPushButton, QLabel, QFileDialog,
    QHBoxLayout, QVBoxLayout, QFrame, QGroupBox, QComboBox,
)


# Provider id → (显示名, 默认 base_url 占位提示)
_PROVIDERS = (
    ("deepseek", "DeepSeek",                "https://api.deepseek.com"),
    ("doubao",   "豆包·火山引擎",            "https://ark.cn-beijing.volces.com/api/v3"),
    ("openai",   "其它 OpenAI 兼容",         "https://api.openai.com/v1"),
)

# 阶段 key → (显示名, 默认 provider, 默认 model)
_STAGES = (
    ("ideate",     "创意",     "doubao",   "doubao-1-5-thinking-pro-250415"),
    ("script",     "剧本",     "doubao",   "doubao-1-5-thinking-pro-250415"),
    ("storyboard", "分镜",     "deepseek", "deepseek-chat"),
    ("prompts",    "提示词",   "deepseek", "deepseek-chat"),
)


class _ProviderBlock(QWidget):
    """单个 LLM 平台的 base_url + api_key + 测试连接行。"""

    def __init__(self, pid: str, label: str, default_base_url: str, parent=None):
        super().__init__(parent)
        self.pid = pid
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
        form.addRow("Base URL", self.base_url_edit)
        form.addRow("API Key", self.api_key_edit)

        bar = QHBoxLayout()
        self.btn_test = QPushButton("测试连接")
        self.test_model_edit = QLineEdit()
        self.test_model_edit.setPlaceholderText("用什么 model 测试（必填）")
        self.test_model_edit.setMaximumWidth(240)
        self.lbl_status = QLabel("")
        bar.addWidget(self.btn_test)
        bar.addWidget(self.test_model_edit)
        bar.addWidget(self.lbl_status, 1)
        form.addRow("", self._wrap(bar))

        self.btn_test.clicked.connect(self._on_test)

    @staticmethod
    def _wrap(layout):
        w = QWidget(); w.setLayout(layout); return w

    def _on_test(self):
        self.lbl_status.setText("测试中…")
        self.lbl_status.setStyleSheet("color: #9aa0a6")
        self.lbl_status.repaint()
        base_url = self.base_url_edit.text().strip() or self._default_base_url
        api_key = self.api_key_edit.text().strip()
        model = self.test_model_edit.text().strip()
        if not api_key:
            self.lbl_status.setText("✗ 未填 API Key")
            self.lbl_status.setStyleSheet("color: #ff5c5c")
            return
        if not model:
            self.lbl_status.setText("✗ 测试 model 必填")
            self.lbl_status.setStyleSheet("color: #ff5c5c")
            return
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=15.0)
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=4, stream=False)
            txt = (resp.choices[0].message.content or "").strip()
            self.lbl_status.setText(f"✓ 通 · 回复 {len(txt)} 字符")
            self.lbl_status.setStyleSheet("color: #4ec98f")
        except Exception as e:
            msg = str(e)[:80]
            self.lbl_status.setText(f"✗ {msg}")
            self.lbl_status.setStyleSheet("color: #ff5c5c")

    def load(self, base_url: str, api_key: str):
        self.base_url_edit.setText(base_url or "")
        self.api_key_edit.setText(api_key or "")

    def values(self) -> tuple[str, str]:
        return (self.base_url_edit.text().strip(),
                self.api_key_edit.text().strip())


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
        root.setContentsMargins(20, 12, 20, 12)
        root.setSpacing(8)

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

        # —— LLM 平台 ——
        sep = QFrame(); sep.setFrameShape(QFrame.HLine); root.addWidget(sep)
        root.addWidget(QLabel("LLM 平台（每个平台 base_url + key 配一次；下方阶段下拉引用）"))
        self._providers: dict[str, _ProviderBlock] = {}
        for pid, label, default_base in _PROVIDERS:
            blk = _ProviderBlock(pid, label, default_base)
            self._providers[pid] = blk
            root.addWidget(blk)

        # —— 阶段使用映射 ——
        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine); root.addWidget(sep2)
        root.addWidget(QLabel("各阶段用哪个平台 + model"))
        stage_form = QFormLayout()
        stage_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        stage_form.setHorizontalSpacing(12); stage_form.setVerticalSpacing(6)
        stage_form.setContentsMargins(0, 0, 0, 0)
        self._stage_widgets: dict[str, tuple[QComboBox, QLineEdit]] = {}
        for skey, slabel, _default_pid, _default_model in _STAGES:
            combo = QComboBox()
            for pid, plabel, _ in _PROVIDERS:
                combo.addItem(plabel, pid)
            model_edit = QLineEdit()
            model_edit.setPlaceholderText("model id（按所选平台填）")
            wrap = QHBoxLayout()
            wrap.addWidget(combo)
            wrap.addWidget(model_edit, 1)
            wrap_w = QWidget(); wrap_w.setLayout(wrap)
            wrap_w.setMaximumWidth(480)
            stage_form.addRow(slabel, wrap_w)
            self._stage_widgets[skey] = (combo, model_edit)
        root.addLayout(stage_form)

        # —— 提示词模板说明 ——
        sep3 = QFrame(); sep3.setFrameShape(QFrame.HLine); root.addWidget(sep3)
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

        # provider 配置
        providers_cfg = getattr(cfg, "screenwriter_providers", None) or {}
        # 向后兼容：旧扁平字段 → 默认填到 DeepSeek
        legacy_url = getattr(cfg, "screenwriter_llm_base_url", "") or ""
        legacy_key = getattr(cfg, "screenwriter_llm_api_key", "") or ""
        for pid, _label, _default in _PROVIDERS:
            pc = providers_cfg.get(pid) or {}
            base = pc.get("base_url", legacy_url if pid == "deepseek" else "")
            api = pc.get("api_key", legacy_key if pid == "deepseek" else "")
            self._providers[pid].load(base, api)

        # 阶段映射
        assignments = getattr(cfg, "screenwriter_stage_assignments", None) or {}
        legacy_models = getattr(cfg, "screenwriter_models", None) or {}
        for skey, _slabel, default_pid, default_model in _STAGES:
            asn = assignments.get(skey) or {}
            pid = asn.get("provider", default_pid)
            model = asn.get("model", legacy_models.get(skey) or default_model)
            combo, model_edit = self._stage_widgets[skey]
            idx = combo.findData(pid)
            if idx < 0:
                idx = 0
            combo.setCurrentIndex(idx)
            model_edit.setText(model)

    def save_to(self, cfg):
        # provider 配置
        providers_out = {}
        for pid, _label, _ in _PROVIDERS:
            base, api = self._providers[pid].values()
            if base or api:
                providers_out[pid] = {"base_url": base, "api_key": api}
        # 阶段映射
        assignments_out = {}
        for skey, _slabel, _default_pid, _default_model in _STAGES:
            combo, model_edit = self._stage_widgets[skey]
            assignments_out[skey] = {
                "provider": combo.currentData() or "",
                "model": model_edit.text().strip(),
            }
        cfg.update_settings(
            screenwriter_project_root=self.project_root_edit.text().strip(),
            screenwriter_providers=providers_out,
            screenwriter_stage_assignments=assignments_out,
        )

    def validate(self):
        return (True, "")

    def cancel_workers(self):
        pass
