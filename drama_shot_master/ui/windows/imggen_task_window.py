"""图片生成任务窗：内嵌 ImgGenPanel，转发状态/结果/脏标记/关闭。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMainWindow

from drama_shot_master.config import Config
from drama_shot_master.core.imggen_task_store import ImgGenTask
from drama_shot_master.ui.panels.imggen_panel import ImgGenPanel
from drama_shot_master.ui.theme import apply_dark_titlebar


class ImgGenTaskWindow(QMainWindow):
    statusChanged = Signal(str, str)
    resultReady = Signal(str, str)
    dirty = Signal(str, dict)
    closed = Signal(str)

    def __init__(self, task: ImgGenTask, cfg: Config, parent=None):
        super().__init__(parent)
        self.task_id = task.id
        self.cfg = cfg
        self.setWindowTitle(f"图片生成 · {task.name}")
        self.resize(720, 780)
        self.panel = ImgGenPanel(cfg, payload=task.payload)
        self.setCentralWidget(self.panel)
        self.panel.statusChanged.connect(lambda s: self.statusChanged.emit(self.task_id, s))
        self.panel.resultReady.connect(lambda p: self.resultReady.emit(self.task_id, p))
        self.panel.dirty.connect(lambda: self.dirty.emit(self.task_id, self.panel.to_payload()))

    def set_title_name(self, name: str):
        self.setWindowTitle(f"图片生成 · {name}")

    def showEvent(self, e):
        super().showEvent(e)
        if not getattr(self, "_themed", False):
            self._themed = True
            apply_dark_titlebar(self)

    def closeEvent(self, e):
        self.dirty.emit(self.task_id, self.panel.to_payload())
        self.closed.emit(self.task_id)
        super().closeEvent(e)
