"""StreamWorker 三参签名（含 project_dir）的回归测试。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter.stream_worker import StreamWorker


def _app():
    return QApplication.instance() or QApplication([])


class _StubClient:
    def __init__(self, evs):
        self._evs = evs

    def stream_post(self, path, body, params=None):
        for ev in self._evs:
            yield ev


def test_event_signal_includes_project_dir():
    _app()
    captured = []
    w = StreamWorker(_StubClient([{"event": "delta", "data": {"text": "hi"}}]),
                     "/x", {}, params=None, project_dir="/tmp/projA")
    w.event.connect(lambda en, dd, pd: captured.append((en, dd, pd)))
    w.run()  # 同步跑（不调 start）
    assert captured == [("delta", {"text": "hi"}, "/tmp/projA")]


def test_finished_signal_carries_project_dir():
    _app()
    got = []
    w = StreamWorker(_StubClient([]), "/x", {}, params=None,
                     project_dir="/tmp/projB")
    w.finished_ok.connect(got.append)
    w.run()
    assert got == ["/tmp/projB"]


def test_failed_signal_carries_project_dir():
    _app()
    class _Bad:
        def stream_post(self, *a, **k):
            raise RuntimeError("boom")
    got = []
    w = StreamWorker(_Bad(), "/x", {}, params=None, project_dir="/tmp/projC")
    w.failed.connect(lambda msg, pd: got.append((msg, pd)))
    w.run()
    assert got == [("boom", "/tmp/projC")]


def test_project_dir_required_positional():
    _app()
    # 老签名（缺 project_dir）必须报错
    import pytest
    with pytest.raises(TypeError):
        StreamWorker(_StubClient([]), "/x", {}, params=None)
