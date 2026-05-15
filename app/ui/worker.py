"""通用 QThread Worker：把任何耗时同步函数搬到后台线程，避免冻结 UI。"""
from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QThread, Signal


class FunctionWorker(QThread):
    """跑一个可调用对象，完成时发 finished_with_result，失败时发 failed。"""
    finished_with_result = Signal(object)
    failed = Signal(str)

    def __init__(self, func: Callable[..., Any], *args, **kwargs):
        super().__init__()
        self._func = func
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            result = self._func(*self._args, **self._kwargs)
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")
            return
        self.finished_with_result.emit(result)


class BatchWorker(QThread):
    """批量任务 worker：调用方传入 items 列表 + 单项 worker 函数。
    每完成一项发 item_done(idx, total, base_name, status, payload_or_error)。
    全部结束发 all_done(ok, failed)。"""
    item_done = Signal(int, int, str, str, object)
    all_done = Signal(int, int)

    def __init__(self,
                 items: list[dict],
                 worker_func: Callable[[dict], Any]):
        super().__init__()
        self._items = items
        self._worker_func = worker_func
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        ok = 0
        failed = 0
        total = len(self._items)
        for idx, item in enumerate(self._items):
            if self._cancel:
                break
            base_name = item.get("base_name", str(idx))
            try:
                payload = self._worker_func(item)
                status = payload.get("status", "ok") if isinstance(payload, dict) else "ok"
                if status == "ok":
                    ok += 1
                self.item_done.emit(idx, total, base_name, status, payload)
            except Exception as e:
                failed += 1
                self.item_done.emit(idx, total, base_name, "failed",
                                    f"{type(e).__name__}: {e}")
        self.all_done.emit(ok, failed)
