"""RunningHub 配置 section（API key / base_url / 连通测试）。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QPushButton, QLabel,
    QHBoxLayout, QVBoxLayout,
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

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        form.addRow("API Key", self.api_key_edit)

        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText("https://www.runninghub.cn")
        form.addRow("Base URL", self.base_url_edit)

        root.addLayout(form)

        bar = QHBoxLayout()
        self.btn_test = QPushButton("连通测试")
        self.lbl_test = QLabel("")
        bar.addWidget(self.btn_test)
        bar.addWidget(self.lbl_test, 1)
        root.addLayout(bar)
        root.addStretch(1)

        self.btn_test.clicked.connect(self._on_test)

    def load_from(self, cfg):
        self.api_key_edit.setText(getattr(cfg, "runninghub_api_key", "") or "")
        self.base_url_edit.setText(
            getattr(cfg, "runninghub_base_url", "") or "https://www.runninghub.cn"
        )

    def save_to(self, cfg):
        cfg.runninghub_api_key = self.api_key_edit.text().strip()
        cfg.runninghub_base_url = (
            self.base_url_edit.text().strip() or "https://www.runninghub.cn"
        )

    def validate(self):
        return (True, "")

    def cancel_workers(self):
        """dialog 关闭时调用，取消未完成的连通测试 worker。"""
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(500)
            self._worker = None

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
