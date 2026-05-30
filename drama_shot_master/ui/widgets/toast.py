"""Toast：自包含的轻提示标签（不依赖 app-shell 状态栏，pop-out 窗也可用）。

用法：
    from drama_shot_master.ui.widgets.toast import show_toast
    show_toast(self, "✓ 已复制到剪贴板")

设计：作为 parent 的子控件，底部居中悬浮，自动 raise，msec 后自动隐藏。
每个 parent 复用同一个 Toast 实例（存于 parent._toast_widget）。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QWidget


class Toast(QLabel):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            "QLabel#Toast{background:rgba(40,60,46,235);color:#a7f3d0;"
            "border:1px solid #3d6b4f;border-radius:6px;"
            "padding:6px 14px;font-size:12px;font-weight:600;}")
        self.hide()

    def show_message(self, text: str, msec: int = 1400) -> None:
        self.setText(text)
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()
        QTimer.singleShot(msec, self.hide)

    def _reposition(self) -> None:
        p = self.parentWidget()
        if p is None:
            return
        x = (p.width() - self.width()) // 2
        y = p.height() - self.height() - 24
        self.move(max(0, x), max(0, y))


def show_toast(parent: QWidget, text: str, msec: int = 1400) -> Toast:
    """在 parent 上显示一条轻提示；同一 parent 复用一个 Toast 实例。"""
    t = getattr(parent, "_toast_widget", None)
    if t is None or not isinstance(t, Toast):
        t = Toast(parent)
        parent._toast_widget = t
    t.show_message(text, msec)
    return t
