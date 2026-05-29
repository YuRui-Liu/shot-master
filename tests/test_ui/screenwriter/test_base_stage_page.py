"""_BaseStagePage worker dict 化的最小契约测试。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter.base_stage_page import _BaseStagePage


def _app():
    return QApplication.instance() or QApplication([])


class _Sub(_BaseStagePage):
    """最小可实例化子类。"""
    def set_project(self, path):
        self._project_dir = path


class _FakeWorker:
    def __init__(self, running=True):
        self._running = running
    def isRunning(self):
        return self._running


def test_default_fields_initialized():
    _app()
    s = _Sub(client=None)
    assert s._workers == {}
    assert s._buf_by_project == {}
    assert s._state_by_project == {}
    assert s._error_by_project == {}
    assert s._project_dir is None


def test_is_streaming_false_when_no_worker(tmp_path):
    _app()
    s = _Sub(client=None)
    assert s.is_streaming(tmp_path) is False


def test_is_streaming_true_when_worker_running(tmp_path):
    _app()
    s = _Sub(client=None)
    s._workers[tmp_path] = _FakeWorker(running=True)
    assert s.is_streaming(tmp_path) is True


def test_is_streaming_false_when_worker_stopped(tmp_path):
    _app()
    s = _Sub(client=None)
    s._workers[tmp_path] = _FakeWorker(running=False)
    assert s.is_streaming(tmp_path) is False


def test_active_worker_returns_current_projects_worker(tmp_path):
    _app()
    s = _Sub(client=None)
    s._project_dir = tmp_path
    w = _FakeWorker(running=True)
    s._workers[tmp_path] = w
    assert s._active_worker() is w


def test_active_worker_returns_none_when_no_current_project():
    _app()
    s = _Sub(client=None)
    assert s._active_worker() is None


def test_on_project_switched_default_noop(tmp_path):
    _app()
    s = _Sub(client=None)
    # 默认实现不应抛
    s._on_project_switched(None, tmp_path)
