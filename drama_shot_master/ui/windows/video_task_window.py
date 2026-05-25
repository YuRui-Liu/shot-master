"""VideoTaskWindow：单个视频生成任务的独立顶级窗口。"""
from __future__ import annotations

from PySide6.QtCore import QEvent, Signal
from PySide6.QtWidgets import QMainWindow

from drama_shot_master.config import Config
from drama_shot_master.core.video_timeline_model import TimelineModel
from drama_shot_master.core.video_task_store import VideoTask
from drama_shot_master.ui.state import AppState
from drama_shot_master.ui.panels.video_panel import VideoPanel


class VideoTaskWindow(QMainWindow):
    """内嵌一个 VideoPanel 编辑器；提交独立、并行。"""

    statusChanged = Signal(str, str)     # (task_id, status_text)
    resultReady = Signal(str, str)       # (task_id, mp4_path)
    timelineDirty = Signal(str, dict)    # (task_id, timeline_dict)
    closed = Signal(str)                 # (task_id)

    def __init__(self, task: VideoTask, state: AppState, cfg: Config,
                 parent=None):
        super().__init__(parent)
        self._task_id = task.id
        self.model = TimelineModel.from_dict(task.timeline)
        self.editor = VideoPanel(state, cfg, self.model)
        self.setCentralWidget(self.editor)
        self.setWindowTitle(f"视频任务 · {task.name}")
        self.resize(1100, 820)

        self.editor.submitStarted.connect(
            lambda: self.statusChanged.emit(self._task_id, "生成中"))
        self.editor.submitDone.connect(self._on_done)
        self.editor.submitFailed.connect(
            lambda e: self.statusChanged.emit(self._task_id, "失败"))

    @property
    def task_id(self) -> str:
        return self._task_id

    def set_title_name(self, name: str) -> None:
        self.setWindowTitle(f"视频任务 · {name}")

    def _persist(self) -> None:
        self.timelineDirty.emit(self._task_id, self.model.to_dict())

    def _on_done(self, mp4: str) -> None:
        self.statusChanged.emit(self._task_id, "完成")
        self.resultReady.emit(self._task_id, mp4)

    def changeEvent(self, event):
        if event.type() == QEvent.WindowDeactivate:
            self._persist()
        super().changeEvent(event)

    def closeEvent(self, event):
        # 停本地轮询（云端可能仍跑）；断开提交转发信号。
        # 注意：本窗不设 WA_DeleteOnClose、不 deleteLater，关窗后 editor 仍存活，
        # 故 worker 的 QTimer 回调即便在关窗后触发也只更新隐藏的 status bar，无
        # use-after-free。若日后加 WA_DeleteOnClose，须改为带存活判断的回调。
        try:
            self.editor._cancel_flag["v"] = True
            self.editor.submitStarted.disconnect()
            self.editor.submitDone.disconnect()
            self.editor.submitFailed.disconnect()
        except (RuntimeError, TypeError):
            pass
        self._persist()
        self.closed.emit(self._task_id)
        super().closeEvent(event)
