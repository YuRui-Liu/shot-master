"""VideoStatusBar：底部状态栏 + 提交/取消按钮。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton


class VideoStatusBar(QWidget):
    """状态机：idle / uploading / status / done / failed。"""

    submitRequested = Signal()
    cancelRequested = Signal()
    openFolderRequested = Signal(object)   # Path

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        self.status_label = QLabel("空闲")
        self.status_label.setTextFormat(Qt.RichText)
        self.status_label.setOpenExternalLinks(False)
        self.status_label.linkActivated.connect(self._on_link)
        layout.addWidget(self.status_label, 1)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.cancelRequested)
        layout.addWidget(self.cancel_btn)

        self.submit_btn = QPushButton("🎬 提交")
        self.submit_btn.clicked.connect(self.submitRequested)
        layout.addWidget(self.submit_btn)

    # ---------- 状态机 API ----------

    def set_idle(self):
        self.status_label.setText("空闲")
        self.submit_btn.setEnabled(True)
        self.cancel_btn.setVisible(False)

    def set_uploading(self, done: int, total: int, name: str):
        self.status_label.setText(f"上传 {done}/{total}：{name}")
        self.submit_btn.setEnabled(False)
        self.cancel_btn.setVisible(True)

    def set_status(self, status: str):
        self.status_label.setText(f"任务状态：{status}")
        self.submit_btn.setEnabled(False)
        self.cancel_btn.setVisible(True)

    def set_done(self, mp4_path: Path):
        self.status_label.setText(
            f'<span style="color:#5fa">✓ 完成：'
            f'<a href="open:{mp4_path}" '
            f'style="color:#7fc">{mp4_path.name}</a></span>')
        self.submit_btn.setEnabled(True)
        self.cancel_btn.setVisible(False)

    def set_failed(self, reason: str):
        msg = reason[:120] + ("…" if len(reason) > 120 else "")
        self.status_label.setText(
            f'<span style="color:#f66">✗ 失败：{msg}</span>')
        self.submit_btn.setEnabled(True)
        self.cancel_btn.setVisible(False)

    # ---------- 内部 ----------

    def _on_link(self, link: str):
        if link.startswith("open:"):
            self.openFolderRequested.emit(Path(link[5:]).parent)
