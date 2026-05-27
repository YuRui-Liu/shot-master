"""ProjectCommandBar：AppShell 顶部全局命令栏（项目上下文头）。

补回旧 MainWindow 左栏丢失的目录入口：打开目录 / 设置输出目录，以及当前目录、
输出目录、图片计数三段只读文本。自身只发信号（openDirRequested /
setOutputRequested），具体动作由 AppShell 接。

单行横向布局：
    [打开目录] 当前: <dir>   [设置输出] 输出: <output>   <count>
末尾留 stretch 使整体靠左对齐。
"""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel

try:  # nicer Fluent look; falls back to plain QPushButton if unavailable
    from qfluentwidgets import PushButton as _Button
except Exception:  # pragma: no cover - defensive, verified present in 1.11.2
    from PySide6.QtWidgets import QPushButton as _Button


class ProjectCommandBar(QWidget):
    openDirRequested = Signal()
    setOutputRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        self.btn_open_dir = _Button("打开目录")
        self.btn_open_dir.clicked.connect(self.openDirRequested)
        layout.addWidget(self.btn_open_dir)

        layout.addWidget(QLabel("当前:"))
        self.lbl_dir = QLabel("未打开")
        self.lbl_dir.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.lbl_dir)

        layout.addSpacing(16)

        self.btn_set_output = _Button("设置输出目录")
        self.btn_set_output.clicked.connect(self.setOutputRequested)
        layout.addWidget(self.btn_set_output)

        layout.addWidget(QLabel("输出:"))
        self.lbl_output = QLabel("未设置")
        self.lbl_output.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.lbl_output)

        layout.addSpacing(16)

        self.lbl_count = QLabel("0 张  已选 0")
        layout.addWidget(self.lbl_count)

        layout.addStretch(1)

    # ---------- 文本 API ----------

    def set_dir(self, text: str) -> None:
        self.lbl_dir.setText(text or "未打开")

    def set_output(self, text: str) -> None:
        self.lbl_output.setText(text or "未设置")

    def set_count(self, text: str) -> None:
        self.lbl_count.setText(text)

    def count_text(self) -> str:
        return self.lbl_count.text()
