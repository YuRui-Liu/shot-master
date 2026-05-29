"""VideoTaskManagerPanel icon_rail 接口冒烟测试。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from unittest.mock import MagicMock

def _app():
    return QApplication.instance() or QApplication([])

def test_video_icon_rail_items_empty():
    _app()
    from drama_shot_master.ui.panels.video_task_manager_panel import VideoTaskManagerPanel
    panel = VideoTaskManagerPanel.__new__(VideoTaskManagerPanel)
    store = MagicMock(); store.all.return_value = []
    panel.store = store; panel._live_status = {}
    assert panel.icon_rail_items() == []

def test_video_icon_rail_items_count():
    _app()
    from drama_shot_master.ui.panels.video_task_manager_panel import VideoTaskManagerPanel
    panel = VideoTaskManagerPanel.__new__(VideoTaskManagerPanel)
    t1 = MagicMock(); t1.id = "a"; t1.name = "视频A"
    t2 = MagicMock(); t2.id = "b"; t2.name = "视频B"
    store = MagicMock(); store.all.return_value = [t1, t2]
    panel.store = store; panel._live_status = {}
    items = panel.icon_rail_items()
    assert len(items) == 2

def test_video_icon_rail_items_running():
    _app()
    from drama_shot_master.ui.panels.video_task_manager_panel import VideoTaskManagerPanel
    panel = VideoTaskManagerPanel.__new__(VideoTaskManagerPanel)
    t = MagicMock(); t.id = "x"; t.name = "X"
    store = MagicMock(); store.all.return_value = [t]
    panel.store = store; panel._live_status = {"x": "生成中"}
    assert panel.icon_rail_items()[0].status == "running"

def test_video_icon_rail_items_error():
    _app()
    from drama_shot_master.ui.panels.video_task_manager_panel import VideoTaskManagerPanel
    panel = VideoTaskManagerPanel.__new__(VideoTaskManagerPanel)
    t = MagicMock(); t.id = "x"; t.name = "X"
    store = MagicMock(); store.all.return_value = [t]
    panel.store = store; panel._live_status = {"x": "失败"}
    assert panel.icon_rail_items()[0].status == "error"
