import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QListWidgetItem

from drama_shot_master.core.task_aggregator import TaskRecord
from drama_shot_master.ui.widgets.task_center_dock import TaskCenterDock


def _app():
    return QApplication.instance() or QApplication([])


class _StubAgg:
    def __init__(self, records):
        self._r = records
    def snapshot(self):
        return list(self._r)


@pytest.fixture
def dock():
    _app()
    return TaskCenterDock(_StubAgg([
        TaskRecord("video", "v1", "VIDEO1", "生成中", ""),
        TaskRecord("dub",   "d1", "DUB1",   "失败",   ""),
        TaskRecord("imggen","i1", "IMG1",   "完成",   "/tmp/x.png"),
        TaskRecord("soundtrack","s1","ST1", "完成",   "/tmp/y.mp4"),
        TaskRecord("video", "v2", "VIDEO2", "空闲",   ""),
    ]))


def test_dock_three_groups_populated(dock):
    assert dock.list_running.count() == 1     # v1
    assert dock.list_failed.count() == 1      # d1
    assert dock.list_done.count() == 2        # i1, s1


def test_dock_count_label(dock):
    assert "生成中 1" in dock.lbl_counts.text()
    assert "失败 1" in dock.lbl_counts.text()
    assert "完成 2" in dock.lbl_counts.text()


def test_dock_double_click_emits_task_activated(dock):
    fired = []
    dock.taskActivated.connect(lambda kind, tid: fired.append((kind, tid)))
    item = dock.list_running.item(0)
    dock.list_running.itemDoubleClicked.emit(item)
    assert fired == [("video", "v1")]


def test_dock_recent_complete_capped(monkeypatch):
    _app()
    many_done = [TaskRecord("video", f"v{i}", f"V{i}", "完成", f"/tmp/{i}.mp4")
                 for i in range(30)]
    d = TaskCenterDock(_StubAgg(many_done))
    assert d.list_done.count() == 20
