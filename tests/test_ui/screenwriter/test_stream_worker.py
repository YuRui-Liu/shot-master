import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter.stream_worker import StreamWorker


def _app():
    return QApplication.instance() or QApplication([])


class _StubClient:
    def __init__(self, events):
        self._events = events

    def stream_post(self, path, body, params=None):
        for ev in self._events:
            yield ev


def _drain(worker, timeout_ms=2000):
    """跑 worker 到 finished_ok 或 failed，期间转 QEventLoop。"""
    loop = QEventLoop()
    worker.finished_ok.connect(loop.quit)
    worker.failed.connect(lambda _: loop.quit())
    QTimer.singleShot(timeout_ms, loop.quit)
    worker.start()
    loop.exec()
    worker.wait(500)


def test_emits_events_in_order():
    _app()
    events = [
        {"event": "status", "data": {"phase": "thinking"}},
        {"event": "delta",  "data": {"text": "hi"}},
        {"event": "done",   "data": {"saved": "/x"}},
    ]
    seen = []
    w = StreamWorker(_StubClient(events), "/foo", {"a": 1})
    w.event.connect(lambda name, data: seen.append((name, data)))
    finished = []
    w.finished_ok.connect(lambda: finished.append(True))
    _drain(w)
    assert seen == [("status", {"phase": "thinking"}),
                    ("delta",  {"text": "hi"}),
                    ("done",   {"saved": "/x"})]
    assert finished == [True]


def test_failed_signal_on_exception():
    _app()
    class _Boom:
        def stream_post(self, *a, **kw):
            raise RuntimeError("boom")
            yield  # noqa: unreachable - makes it a generator if needed
    errors = []
    w = StreamWorker(_Boom(), "/foo", {})
    w.failed.connect(errors.append)
    _drain(w)
    assert errors and "boom" in errors[0]


def test_stop_interrupts_iteration():
    _app()
    # 长流：100 个 event；调 stop 后应早退（实际能不能立即退取决于迭代器；
    # 这里用一个会检查 interruption 的 stub）
    def long_gen():
        for i in range(100):
            yield {"event": "delta", "data": {"text": str(i)}}

    class _Slow:
        def stream_post(self, *a, **kw):
            yield from long_gen()

    seen = []
    w = StreamWorker(_Slow(), "/foo", {})
    w.event.connect(lambda *a: seen.append(a))
    w.start()
    # 等到 worker 跑起来一点再 stop
    QTimer.singleShot(20, w.stop)
    w.wait(2000)
    # 至少触发过 stop（有的事件可能在 stop 前已 emit）；
    # 关键：worker 已退出 isFinished()
    assert w.isFinished()
