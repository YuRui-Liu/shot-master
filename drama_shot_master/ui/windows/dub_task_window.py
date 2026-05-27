"""配音任务窗：标题=任务名，内嵌 DubPanel；转发状态/结果/脏标记/关闭信号。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMainWindow

from drama_shot_master.config import Config
from drama_shot_master.core.dub_task_store import DubTask
from drama_shot_master.ui.panels.dub_panel import DubPanel
from drama_shot_master.ui.theme import apply_dark_titlebar


class DubTaskWindow(QMainWindow):
    statusChanged = Signal(str, str)       # (task_id, status)
    resultReady = Signal(str, str)         # (task_id, flac_path)
    dirty = Signal(str, dict)              # (task_id, payload)
    closed = Signal(str)                   # (task_id)

    def __init__(self, task: DubTask, cfg: Config, parent=None):
        super().__init__(parent)
        self.task_id = task.id
        self.cfg = cfg
        self.setWindowTitle(f"配音 · {task.name}")
        self.resize(1100, 820)        # 与视频/配乐任务窗一致
        self.panel = DubPanel(cfg, payload=task.payload)
        self.setCentralWidget(self.panel)
        self.panel.statusChanged.connect(lambda s: self.statusChanged.emit(self.task_id, s))
        self.panel.resultReady.connect(lambda p: self.resultReady.emit(self.task_id, p))
        self.panel.dirty.connect(self._on_dirty)

    def _on_dirty(self):
        self.dirty.emit(self.task_id, self.panel.to_payload())

    def set_title_name(self, name: str):
        self.setWindowTitle(f"配音 · {name}")

    def showEvent(self, e):
        super().showEvent(e)
        if not getattr(self, "_themed", False):
            self._themed = True
            apply_dark_titlebar(self)

    def closeEvent(self, e):
        self.dirty.emit(self.task_id, self.panel.to_payload())
        self.closed.emit(self.task_id)
        super().closeEvent(e)
