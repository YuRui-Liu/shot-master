"""迷你签发界面：粘贴机器码 + 选有效期 → 出激活码 + 记台账。"""
from __future__ import annotations

import csv
import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QFormLayout, QLineEdit, QSpinBox,
    QPushButton, QPlainTextEdit, QLabel, QMessageBox,
)

from license_admin import issuer, keygen

ISSUED_CSV = Path(__file__).resolve().parent / "issued.csv"


class AdminWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Drama-Shot-Master 授权签发台")
        self.resize(560, 360)
        self._sk = keygen.load_private_key()
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.machine = QLineEdit(); self.machine.setPlaceholderText("粘贴用户的机器码")
        self.days = QSpinBox(); self.days.setRange(1, 3650); self.days.setValue(90)
        self.lid = QSpinBox(); self.lid.setRange(1, 2_000_000_000)
        self.lid.setValue(self._next_license_id())
        form.addRow("机器码", self.machine)
        form.addRow("有效期(天)", self.days)
        form.addRow("授权流水号", self.lid)
        root.addLayout(form)
        gen = QPushButton("生成激活码"); gen.clicked.connect(self._generate)
        root.addWidget(gen)
        self.out = QPlainTextEdit(); self.out.setReadOnly(True)
        root.addWidget(self.out, 1)
        cp = QPushButton("复制激活码"); cp.clicked.connect(self._copy)
        root.addWidget(cp)
        self.hint = QLabel(""); self.hint.setStyleSheet("color:#888")
        root.addWidget(self.hint)

    def _next_license_id(self) -> int:
        if not ISSUED_CSV.exists():
            return 1
        try:
            rows = list(csv.reader(ISSUED_CSV.open(encoding="utf-8")))
            return max((int(r[0]) for r in rows[1:] if r), default=0) + 1
        except (OSError, ValueError):
            return 1

    def _generate(self):
        code = self.machine.text().strip()
        if not code:
            QMessageBox.warning(self, "缺少机器码", "请先粘贴用户的机器码")
            return
        try:
            out = issuer.issue(code, self.days.value(), self.lid.value(), self._sk)
        except Exception as e:                          # 机器码格式错误等
            QMessageBox.critical(self, "签发失败", str(e))
            return
        self.out.setPlainText(out)
        self._record(code, out)
        self.hint.setText(f"已签发 流水号 {self.lid.value()}，有效期 {self.days.value()} 天")
        self.lid.setValue(self.lid.value() + 1)

    def _record(self, machine_code: str, code: str):
        new = not ISSUED_CSV.exists()
        with ISSUED_CSV.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["license_id", "machine_code", "days", "issued_at"])
            w.writerow([self.lid.value(), machine_code, self.days.value(),
                        datetime.datetime.now().isoformat(timespec="seconds")])

    def _copy(self):
        QApplication.clipboard().setText(self.out.toPlainText())
        self.hint.setText("已复制到剪贴板")


def main():
    app = QApplication([])
    w = AdminWindow(); w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
