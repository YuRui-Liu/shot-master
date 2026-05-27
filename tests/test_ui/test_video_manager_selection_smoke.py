import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.config import load_config
from drama_shot_master.ui.state import AppState
from drama_shot_master.core.video_task_store import VideoTaskStore
from drama_shot_master.ui.panels.video_task_manager_panel import VideoTaskManagerPanel


def _app():
    return QApplication.instance() or QApplication([])


def _panel():
    store = VideoTaskStore.from_list([])
    store.add("任务A", {}); store.add("任务B", {})
    return VideoTaskManagerPanel(AppState(), load_config(), store,
                                 None, None, lambda: None), store


def test_selecting_row_emits_task_selected():
    _app()
    panel, store = _panel()
    seen = []
    panel.taskSelected.connect(seen.append)
    panel.table.setCurrentCell(0, 0)
    assert seen and seen[-1].id == store.all()[0].id


def test_open_close_cb_optional_none_safe():
    _app()
    store = VideoTaskStore.from_list([])
    panel = VideoTaskManagerPanel(AppState(), load_config(), store,
                                  None, None, lambda: None)
    panel._on_new()             # None open cb 不抛
    assert len(store.all()) == 1
