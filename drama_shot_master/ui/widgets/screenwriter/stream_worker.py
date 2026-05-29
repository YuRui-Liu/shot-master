"""SSE 流式 worker：阻塞迭代器 → Qt 信号流，避免堵 UI 线程。

设计参考：spec §2。单次用完即抛——每次生成新建 StreamWorker，
不复用，避免状态污染。
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class StreamWorker(QThread):
    """SSE 流式 worker。"""
    event = Signal(str, dict)       # (event_name, data_dict)
    finished_ok = Signal()          # 流自然结束
    failed = Signal(str)            # 异常（网络/解析）

    def __init__(self, client, path: str, body: dict,
                 params: dict | None = None, parent=None):
        super().__init__(parent)
        self._client = client
        self._path = path
        self._body = body
        self._params = params or {}

    def run(self):
        try:
            for ev in self._client.stream_post(self._path, self._body,
                                                params=self._params):
                if self.isInterruptionRequested():
                    return
                self.event.emit(ev.get("event", ""), ev.get("data", {}))
            self.finished_ok.emit()
        except Exception as e:
            self.failed.emit(str(e))

    def stop(self):
        """主线程槽里调；线程检测到 interruption flag 后退循环。"""
        self.requestInterruption()
