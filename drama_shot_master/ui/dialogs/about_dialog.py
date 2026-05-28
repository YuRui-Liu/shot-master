"""关于 + 激活对话框：开发者信息 / 授权状态 / 机器码 / 激活码输入。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QGroupBox, QMessageBox,
)

from drama_shot_master.config import Config
from drama_shot_master.licensing import manager
from drama_shot_master.licensing.fingerprint import machine_code

_APP_NAME = "Drama-Shot-Master"
_COPYRIGHT = "© 2026"          # 作者按需补全署名/联系方式


def _app_version() -> str:
    try:
        from importlib.metadata import version
        return version("drama-shot-master")
    except Exception:
        return "dev"


def _status_text(st: manager.LicenseStatus) -> tuple[str, str]:
    S = manager.LicenseState
    if st.state is S.VALID:
        return (f"已激活，有效期至 {st.expiry_date}（剩 {st.days_left} 天）", "#2BAA4A")
    if st.state is S.EXPIRED:
        return (f"已过期（{st.expiry_date}），请输入新激活码", "#D9544D")
    if st.state is S.WRONG_MACHINE:
        return ("此激活码非本机，请用本机机器码重新申请", "#D9544D")
    if st.state is S.TAMPERED:
        return ("激活码无效或已损坏", "#D9544D")
    return ("未激活", "#D9544D")


class AboutDialog(QDialog):
    def __init__(self, cfg: Config, parent=None, activation_focus: bool = False):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("关于")
        self.setModal(True)
        self.resize(520, 460)
        self._build_ui()
        self._refresh_status()

    def _build_ui(self):
        root = QVBoxLayout(self)

        info = QGroupBox("开发者信息")
        iv = QVBoxLayout(info)
        iv.addWidget(QLabel(f"<b>{_APP_NAME}</b><br>"
                     f"版本：v{_app_version()}<br>"
                     "作者：二进制糯米<br>"
                     "邮箱：1062283553@qq.com<br>"
                     "二进制糯米 版权所有<br>"
                     "本软件仅限合法使用，禁止二次分发"))
        iv.addWidget(QLabel(_COPYRIGHT))
        root.addWidget(info)

        lic = QGroupBox("授权")
        lv = QVBoxLayout(lic)
        self.status_label = QLabel("…")
        self.status_label.setWordWrap(True)
        lv.addWidget(self.status_label)

        mc = QHBoxLayout()
        self.machine_label = QLabel(machine_code())
        self.machine_label.setTextInteractionFlags(
            self.machine_label.textInteractionFlags() | Qt.TextSelectableByMouse)
        mc.addWidget(QLabel("机器码:"))
        mc.addWidget(self.machine_label, 1)
        copy = QPushButton("复制机器码"); copy.clicked.connect(self._copy_machine)
        mc.addWidget(copy)
        lv.addLayout(mc)

        lv.addWidget(QLabel("激活码（粘贴后点激活）:"))
        self.code_input = QPlainTextEdit(); self.code_input.setFixedHeight(90)
        lv.addWidget(self.code_input)
        act = QPushButton("激活"); act.setObjectName("AccentButton")
        act.clicked.connect(self._activate)
        lv.addWidget(act)
        root.addWidget(lic)

    def _refresh_status(self):
        text, color = _status_text(manager.status())
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color:{color}; font-weight:bold;")

    def _copy_machine(self):
        QApplication.clipboard().setText(self.machine_label.text())

    def _activate(self):
        code = self.code_input.toPlainText().strip()
        if not code:
            return
        st = manager.activate(code)
        self._refresh_status()
        if manager.gate_allows(st.state):
            QMessageBox.information(self, "激活成功", "授权已生效。")
            self.accept()
        else:
            text, _ = _status_text(st)
            QMessageBox.warning(self, "激活失败", text)
