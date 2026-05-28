import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.panels.video_task_manager_panel import VideoTaskManagerPanel
from drama_shot_master.ui.panels.dub_task_manager_panel import DubTaskManagerPanel
from drama_shot_master.ui.panels.imggen_task_manager_panel import ImgGenTaskManagerPanel
from drama_shot_master.core.video_task_store import VideoTaskStore
from drama_shot_master.core.dub_task_store import DubTaskStore
from drama_shot_master.core.imggen_task_store import ImgGenTaskStore


def _app():
    return QApplication.instance() or QApplication([])


def test_video_manager_get_status():
    _app()
    m = VideoTaskManagerPanel(None, None, VideoTaskStore(), None, None, lambda: None)
    assert m.get_status("nonexistent") == "空闲"
    m._live_status["t1"] = "生成中"
    assert m.get_status("t1") == "生成中"


def test_dub_manager_get_status():
    _app()
    m = DubTaskManagerPanel(None, None, DubTaskStore(), None, None, lambda: None)
    assert m.get_status("nonexistent") == "空闲"
    m._live_status["t1"] = "失败"
    assert m.get_status("t1") == "失败"


def test_imggen_manager_get_status():
    _app()
    m = ImgGenTaskManagerPanel(None, None, ImgGenTaskStore(), None, None, lambda: None)
    assert m.get_status("nonexistent") == "空闲"
    m._live_status["t1"] = "完成"
    assert m.get_status("t1") == "完成"
