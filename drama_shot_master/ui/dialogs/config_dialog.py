"""mp4 路径 / 风格 / 输出目录 编辑弹窗。"""
from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QFileDialog, QDialogButtonBox,
)


class ConfigDialog(QDialog):
    def __init__(self, initial: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("任务配置")
        self.setMinimumWidth(450)
        self._build_ui(initial)

    def _build_ui(self, initial: dict):
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("成片 MP4:"))
        mp4_row = QHBoxLayout()
        self.mp4_edit = QLineEdit(initial.get("mp4", ""))
        b1 = QPushButton("浏览…")
        b1.clicked.connect(self._browse_mp4)
        mp4_row.addWidget(self.mp4_edit, 1)
        mp4_row.addWidget(b1)
        lay.addLayout(mp4_row)
        lay.addWidget(QLabel("总风格:"))
        self.style_edit = QPlainTextEdit(initial.get("style", ""))
        self.style_edit.setMaximumHeight(80)
        lay.addWidget(self.style_edit)
        lay.addWidget(QLabel("本任务输出目录 (空=用全局默认):"))
        out_row = QHBoxLayout()
        self.out_edit = QLineEdit(initial.get("output_dir", ""))
        b2 = QPushButton("浏览…")
        b2.clicked.connect(self._browse_out)
        out_row.addWidget(self.out_edit, 1)
        out_row.addWidget(b2)
        lay.addLayout(out_row)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _browse_mp4(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择成片 MP4", self.mp4_edit.text() or "",
            "视频 (*.mp4 *.mov)")
        if p:
            self.mp4_edit.setText(p)

    def _browse_out(self):
        d = QFileDialog.getExistingDirectory(
            self, "选择输出目录", self.out_edit.text() or "")
        if d:
            self.out_edit.setText(d)

    def to_payload(self) -> dict:
        return {
            "mp4": self.mp4_edit.text().strip(),
            "style": self.style_edit.toPlainText().strip(),
            "output_dir": self.out_edit.text().strip(),
        }
