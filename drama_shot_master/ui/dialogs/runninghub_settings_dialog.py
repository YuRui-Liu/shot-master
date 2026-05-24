"""RunningHubSettingsDialog：菜单栏「设置 → RunningHub…」打开。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QLabel, QFileDialog, QRadioButton, QButtonGroup, QCheckBox, QWidget,
    QDialogButtonBox, QMessageBox, QFrame,
)

from drama_shot_master.config import Config
from drama_shot_master.providers.runninghub import (
    RunningHubClient, RunningHubUnavailable, RunningHubTaskFailed,
)
from drama_shot_master.ui.worker import FunctionWorker


class RunningHubSettingsDialog(QDialog):
    """配置 api_key / 输出目录 / 提交模式 / base_url / 模板。"""

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._worker: FunctionWorker | None = None
        self.setWindowTitle("RunningHub 配置")
        self.setModal(True)
        self.resize(560, 460)
        self._build_ui()
        self._load_from_cfg()

    def _build_ui(self):
        root = QVBoxLayout(self)
        form = QFormLayout()

        # API Key
        key_row = QHBoxLayout()
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.show_key_btn = QPushButton("👁")
        self.show_key_btn.setCheckable(True)
        self.show_key_btn.setMaximumWidth(40)
        self.show_key_btn.toggled.connect(self._toggle_key_visibility)
        key_row.addWidget(self.api_key_edit, 1)
        key_row.addWidget(self.show_key_btn)
        key_wrap = QWidget(); key_wrap.setLayout(key_row)
        form.addRow("API Key", key_wrap)

        # Base URL
        self.base_url_edit = QLineEdit()
        form.addRow("Base URL", self.base_url_edit)

        # 视频输出目录
        out_row = QHBoxLayout()
        self.video_out_edit = QLineEdit()
        self.video_out_edit.setPlaceholderText("空=用 state.output_dir")
        b = QPushButton("浏览…")
        b.clicked.connect(self._browse_video_out)
        out_row.addWidget(self.video_out_edit, 1)
        out_row.addWidget(b)
        out_wrap = QWidget(); out_wrap.setLayout(out_row)
        form.addRow("视频输出目录", out_wrap)

        # 提交模式
        mode_row = QHBoxLayout()
        self.mode_inline_btn = QRadioButton("Inline（推荐）")
        self.mode_id_btn = QRadioButton("ID + nodeInfoList")
        self.mode_inline_btn.setChecked(True)
        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self.mode_inline_btn)
        self._mode_group.addButton(self.mode_id_btn)
        self.mode_inline_btn.toggled.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_inline_btn)
        mode_row.addWidget(self.mode_id_btn)
        mode_row.addStretch(1)
        mode_wrap = QWidget(); mode_wrap.setLayout(mode_row)
        form.addRow("提交模式", mode_wrap)

        # Workflow ID
        self.workflow_id_edit = QLineEdit()
        self.workflow_id_edit.setPlaceholderText("仅 ID 模式需要")
        self.workflow_id_edit.setEnabled(False)
        form.addRow("Workflow ID", self.workflow_id_edit)

        # 工作流模板
        tpl_row = QHBoxLayout()
        self.use_builtin_cb = QCheckBox("使用内置模板")
        self.use_builtin_cb.setChecked(True)
        self.use_builtin_cb.toggled.connect(self._on_builtin_toggled)
        tpl_row.addWidget(self.use_builtin_cb)
        tpl_wrap = QWidget(); tpl_wrap.setLayout(tpl_row)
        form.addRow(tpl_wrap)

        tpl_path_row = QHBoxLayout()
        self.template_path_edit = QLineEdit()
        self.template_path_edit.setEnabled(False)
        self.template_browse_btn = QPushButton("浏览…")
        self.template_browse_btn.setEnabled(False)
        self.template_browse_btn.clicked.connect(self._browse_template)
        tpl_path_row.addWidget(self.template_path_edit, 1)
        tpl_path_row.addWidget(self.template_browse_btn)
        tpl_path_wrap = QWidget(); tpl_path_wrap.setLayout(tpl_path_row)
        form.addRow("自定义模板路径", tpl_path_wrap)

        root.addLayout(form)

        # 分割线
        line = QFrame(); line.setFrameShape(QFrame.HLine)
        root.addWidget(line)

        # 测试连接
        test_row = QHBoxLayout()
        self.test_btn = QPushButton("🔌 测试连接")
        self.test_btn.clicked.connect(self._on_test_connection)
        self.test_result_label = QLabel("")
        self.test_result_label.setTextFormat(Qt.RichText)
        test_row.addWidget(self.test_btn)
        test_row.addWidget(self.test_result_label, 1)
        root.addLayout(test_row)

        # OK / Cancel
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _load_from_cfg(self):
        self.api_key_edit.setText(self.cfg.runninghub_api_key)
        self.base_url_edit.setText(
            self.cfg.runninghub_base_url or "https://www.runninghub.cn")
        self.video_out_edit.setText(self.cfg.video_output_dir)
        if self.cfg.runninghub_submit_mode == "id":
            self.mode_id_btn.setChecked(True)
        else:
            self.mode_inline_btn.setChecked(True)
        self.workflow_id_edit.setText(self.cfg.runninghub_workflow_id)
        custom_tpl = self.cfg.runninghub_template_path
        if custom_tpl:
            self.use_builtin_cb.setChecked(False)
            self.template_path_edit.setText(custom_tpl)
        else:
            self.use_builtin_cb.setChecked(True)

    # ---------- 槽 ----------

    def _toggle_key_visibility(self, on: bool):
        self.api_key_edit.setEchoMode(
            QLineEdit.Normal if on else QLineEdit.Password)

    def _on_mode_changed(self):
        self.workflow_id_edit.setEnabled(self.mode_id_btn.isChecked())

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

    def _on_test_connection(self):
        api_key = self.api_key_edit.text().strip()
        base_url = self.base_url_edit.text().strip() or "https://www.runninghub.cn"
        if not api_key:
            self.test_result_label.setText(
                '<span style="color:#f66">未填 API Key</span>')
            return
        self.test_result_label.setText("测试中…")
        self.test_btn.setEnabled(False)

        def task():
            try:
                with RunningHubClient(api_key, base_url=base_url) as c:
                    data = c.get_account_status()
                coins = data.get("remainCoins", "?")
                money = data.get("remainMoney", "?")
                currency = data.get("currency", "")
                api_type = data.get("apiType", "?")
                return (True,
                        f"✓ 鉴权通过 · 剩余 {coins} 积分 / {money} {currency} · {api_type}")
            except RunningHubUnavailable as e:
                return False, f"✗ 不可达：{e}"
            except Exception as e:
                return False, f"⚠ 未知错误：{type(e).__name__}: {e}"

        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(self._on_test_done)
        self._worker.failed.connect(
            lambda e: self._on_test_done((False, f"⚠ 内部错：{e}")))
        self._worker.start()

    def _on_test_done(self, result):
        ok, msg = result
        color = "#5fa" if ok else "#f66"
        self.test_result_label.setText(f'<span style="color:{color}">{msg}</span>')
        self.test_btn.setEnabled(True)

    def accept(self):
        api_key = self.api_key_edit.text().strip()
        base_url = self.base_url_edit.text().strip() or "https://www.runninghub.cn"
        mode = "id" if self.mode_id_btn.isChecked() else "inline"
        wf_id = self.workflow_id_edit.text().strip()
        if mode == "id" and not wf_id:
            QMessageBox.warning(
                self, "校验失败",
                "提交模式 = ID 时必须填 Workflow ID")
            return
        template_path = ("" if self.use_builtin_cb.isChecked()
                         else self.template_path_edit.text().strip())
        video_out = self.video_out_edit.text().strip()
        self.cfg.update_settings(
            runninghub_api_key=api_key,
            runninghub_base_url=base_url,
            runninghub_submit_mode=mode,
            runninghub_workflow_id=wf_id,
            runninghub_template_path=template_path,
            video_output_dir=video_out,
        )
        super().accept()
