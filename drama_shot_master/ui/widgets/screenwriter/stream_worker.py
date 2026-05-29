"""SSE 流式 worker：阻塞迭代器 → Qt 信号流，避免堵 UI 线程。

每次生成新建 StreamWorker，不复用。worker 自带 project_dir 字段，
通过 signal 透传，让子面板按当前显示项目分流 UI 更新。
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class StreamWorker(QThread):
    """SSE 流式 worker（每实例绑一个 project_dir）。"""
    event = Signal(str, dict, str)       # (event_name, data, project_dir_str)
    finished_ok = Signal(str)            # project_dir_str
    failed = Signal(str, str)            # (msg, project_dir_str)

    def __init__(self, client, path: str, body: dict,
                 params: dict | None, project_dir, parent=None):
        super().__init__(parent)
        self._client = client
        self._path = path
        self._body = body
        self._params = params or {}
        self._project_dir = str(project_dir)

    def run(self):
        try:
            for ev in self._client.stream_post(
                    self._path, self._body, params=self._params):
                if self.isInterruptionRequested():
                    return
                self.event.emit(
                    ev.get("event", ""), ev.get("data", {}),
                    self._project_dir)
            self.finished_ok.emit(self._project_dir)
        except Exception as e:
            self.failed.emit(str(e), self._project_dir)

    def stop(self):
        self.requestInterruption()

    @property
    def project_dir(self) -> str:
        return self._project_dir
