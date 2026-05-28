"""RunningHub 配置 section（API key / base_url / 视频输出目录 / workflow_ids / 模板 / 连通测试）。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QPushButton, QLabel,
    QHBoxLayout, QVBoxLayout, QCheckBox, QFileDialog, QFrame,
)
from drama_shot_master.ui.worker import FunctionWorker


class RunningHubSection(QWidget):
    title = "RunningHub"
    category = "平台核心"

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._worker: FunctionWorker | None = None
        self._build_ui()
        self.load_from(cfg)

    def _build_ui(self):
        root = QVBoxLayout(self)
        form = QFormLayout()

        # ── API Key ──────────────────────────────────────────────────────────
        key_row = QHBoxLayout()
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.show_key_btn = QPushButton("👁")
        self.show_key_btn.setCheckable(True)
        self.show_key_btn.setMaximumWidth(40)
        self.show_key_btn.toggled.connect(self._toggle_key_visibility)
        key_row.addWidget(self.api_key_edit, 1)
        key_row.addWidget(self.show_key_btn)
        key_wrap = QWidget()
        key_wrap.setLayout(key_row)
        form.addRow("API Key", key_wrap)

        # ── Base URL ─────────────────────────────────────────────────────────
        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText("https://www.runninghub.cn")
        form.addRow("Base URL", self.base_url_edit)

        # ── 视频输出目录 ──────────────────────────────────────────────────────
        out_row = QHBoxLayout()
        self.video_out_edit = QLineEdit()
        self.video_out_edit.setPlaceholderText("空=用 state.output_dir")
        browse_out_btn = QPushButton("浏览…")
        browse_out_btn.clicked.connect(self._browse_video_out)
        out_row.addWidget(self.video_out_edit, 1)
        out_row.addWidget(browse_out_btn)
        out_wrap = QWidget()
        out_wrap.setLayout(out_row)
        form.addRow("视频输出目录", out_wrap)

        # ── Workflow IDs（每个 profile 各一行）────────────────────────────────
        from drama_shot_master.core.workflow_profiles import PROFILES
        self._profiles = PROFILES
        self.workflow_id_edits: dict[str, QLineEdit] = {}
        for key, prof in PROFILES.items():
            edit = QLineEdit()
            edit.setPlaceholderText(f"{prof.name} 的 ID")
            self.workflow_id_edits[key] = edit
            form.addRow(f"{prof.name}ID", edit)

        # ── 工作流模板 ────────────────────────────────────────────────────────
        tpl_row = QHBoxLayout()
        self.use_builtin_cb = QCheckBox("使用内置模板")
        self.use_builtin_cb.setChecked(True)
        self.use_builtin_cb.toggled.connect(self._on_builtin_toggled)
        tpl_row.addWidget(self.use_builtin_cb)
        tpl_wrap = QWidget()
        tpl_wrap.setLayout(tpl_row)
        form.addRow(tpl_wrap)

        tpl_path_row = QHBoxLayout()
        self.template_path_edit = QLineEdit()
        self.template_path_edit.setEnabled(False)
        self.template_browse_btn = QPushButton("浏览…")
        self.template_browse_btn.setEnabled(False)
        self.template_browse_btn.clicked.connect(self._browse_template)
        tpl_path_row.addWidget(self.template_path_edit, 1)
        tpl_path_row.addWidget(self.template_browse_btn)
        tpl_path_wrap = QWidget()
        tpl_path_wrap.setLayout(tpl_path_row)
        form.addRow("自定义模板路径", tpl_path_wrap)

        root.addLayout(form)

        # ── 分割线 ────────────────────────────────────────────────────────────
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        root.addWidget(line)

        # ── 连通测试 ──────────────────────────────────────────────────────────
        bar = QHBoxLayout()
        self.btn_test = QPushButton("🔌 连通测试")
        self.lbl_test = QLabel("")
        self.lbl_test.setTextFormat(Qt.RichText)
        bar.addWidget(self.btn_test)
        bar.addWidget(self.lbl_test, 1)
        root.addLayout(bar)
        root.addStretch(1)

        self.btn_test.clicked.connect(self._on_test)

    # ── load / save / validate ────────────────────────────────────────────────

    def load_from(self, cfg):
        self.api_key_edit.setText(getattr(cfg, "runninghub_api_key", "") or "")
        self.base_url_edit.setText(
            getattr(cfg, "runninghub_base_url", "") or ""
        )
        self.video_out_edit.setText(getattr(cfg, "video_output_dir", "") or "")

        wf_ids = dict(getattr(cfg, "workflow_ids", None) or {})
        legacy = getattr(cfg, "runninghub_workflow_id", "") or ""
        if "director" not in wf_ids and legacy:
            wf_ids["director"] = legacy
        for key, edit in self.workflow_id_edits.items():
            edit.setText(wf_ids.get(key, ""))

        custom_tpl = getattr(cfg, "runninghub_template_path", "") or ""
        if custom_tpl:
            self.use_builtin_cb.setChecked(False)
            self.template_path_edit.setText(custom_tpl)
        else:
            self.use_builtin_cb.setChecked(True)
            self.template_path_edit.clear()

    def save_to(self, cfg):
        api_key = self.api_key_edit.text().strip()
        base_url = self.base_url_edit.text().strip() or "https://www.runninghub.cn"
        video_out = self.video_out_edit.text().strip()
        wf_ids = {key: edit.text().strip()
                  for key, edit in self.workflow_id_edits.items()}
        template_path = ("" if self.use_builtin_cb.isChecked()
                         else self.template_path_edit.text().strip())
        cfg.update_settings(
            runninghub_api_key=api_key,
            runninghub_base_url=base_url,
            video_output_dir=video_out,
            workflow_ids=wf_ids,
            runninghub_workflow_id=wf_ids.get("director", ""),
            runninghub_template_path=template_path,
        )

    def validate(self):
        wf_ids = {key: edit.text().strip()
                  for key, edit in self.workflow_id_edits.items()}
        if not wf_ids.get("director"):
            return (False, "必须填「导演台」的 workflow_id")
        return (True, "")

    # ── helpers ───────────────────────────────────────────────────────────────

    def cancel_workers(self):
        """dialog 关闭时调用，取消未完成的连通测试 worker。"""
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(500)
            self._worker = None

    def _toggle_key_visibility(self, on: bool):
        self.api_key_edit.setEchoMode(
            QLineEdit.Normal if on else QLineEdit.Password)

    def _on_builtin_toggled(self, on: bool):
        self.template_path_edit.setEnabled(not on)
        self.template_browse_btn.setEnabled(not on)
        if on:
            self.template_path_edit.clear()

    def _browse_video_out(self):
        d = QFileDialog.getExistingDirectory(
            self, "选择视频输出目录", self.video_out_edit.text() or "")
        if d:
            self.video_out_edit.setText(d)

    def _browse_template(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择工作流模板", "", "JSON (*.json)")
        if p:
            self.template_path_edit.setText(p)

    def _on_test(self):
        api_key = self.api_key_edit.text().strip()
        base_url = self.base_url_edit.text().strip() or "https://www.runninghub.cn"
        if not api_key:
            self.lbl_test.setText('<span style="color:#f66">未填 API Key</span>')
            return
        self.lbl_test.setText("测试中…")
        self.btn_test.setEnabled(False)

        def task():
            try:
                from drama_shot_master.providers.runninghub import (
                    RunningHubClient, RunningHubUnavailable,
                )
                with RunningHubClient(api_key, base_url=base_url) as c:
                    data = c.get_account_status()
                coins = data.get("remainCoins", "?")
                money = data.get("remainMoney", "?")
                currency = data.get("currency", "")
                api_type = data.get("apiType", "?")
                return (True,
                        f"✓ 鉴权通过 · 剩余 {coins} 积分 / {money} {currency} · {api_type}")
            except Exception as e:
                return False, f"✗ {type(e).__name__}: {e}"

        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(self._on_test_done)
        self._worker.failed.connect(
            lambda e: self._on_test_done((False, f"⚠ 内部错：{e}"))
        )
        self._worker.start()

    def _on_test_done(self, result):
        ok, msg = result
        color = "#5fa" if ok else "#f66"
        self.lbl_test.setText(f'<span style="color:{color}">{msg}</span>')
        self.btn_test.setEnabled(True)
