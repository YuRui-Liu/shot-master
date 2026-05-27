"""DetachedEditorWindow：通用「浮出」窗，承载从主-详详情区 reparent 出来的活编辑器。

只负责承载与转发关闭事件；编辑器的状态/结果/脏信号由 TaskWorkspacePage 统一接线，
故本窗不接任何编辑器信号。关窗时**不删除** editor（page 在 closed 槽里把它收回）。
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMainWindow

from drama_shot_master.ui.theme import apply_window_icon, apply_dark_titlebar


class DetachedEditorWindow(QMainWindow):
    closed = Signal(str)              # task_id

    def __init__(self, editor, title: str, task_id: str, parent=None):
        super().__init__(parent)
        self._task_id = task_id
        self.setWindowTitle(title)
        self.resize(1100, 820)
        self.setCentralWidget(editor)

    @property
    def task_id(self) -> str:
        return self._task_id

    def set_title(self, title: str) -> None:
        self.setWindowTitle(title)

    def showEvent(self, e):
        super().showEvent(e)
        if not getattr(self, "_themed", False):
            self._themed = True
            apply_window_icon(self)
            apply_dark_titlebar(self)

    def closeEvent(self, e):
        self.closed.emit(self._task_id)
        super().closeEvent(e)
