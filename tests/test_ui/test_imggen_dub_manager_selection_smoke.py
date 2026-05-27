import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.config import load_config
from drama_shot_master.ui.state import AppState
from drama_shot_master.core.imggen_task_store import ImgGenTaskStore
from drama_shot_master.core.dub_task_store import DubTaskStore
from drama_shot_master.ui.panels.imggen_task_manager_panel import ImgGenTaskManagerPanel
from drama_shot_master.ui.panels.dub_task_manager_panel import DubTaskManagerPanel


def _app():
    return QApplication.instance() or QApplication([])


def test_imggen_selection_emits_and_loading_guard():
    _app()
    store = ImgGenTaskStore.from_list([])
    store.add("A", payload={}); store.add("B", payload={})
    p = ImgGenTaskManagerPanel(AppState(), load_config(), store, None, None, lambda: None)
    seen = []
    p.taskSelected.connect(seen.append)
    p.table.setCurrentCell(0, 0)
    assert seen and seen[-1].id == store.all()[0].id
    seen.clear()
    p.refresh()
    assert seen == []
    assert hasattr(p, "taskDeleted")


def test_dub_selection_emits():
    _app()
    store = DubTaskStore.from_list([])
    store.add("A", mode="clone", payload={}); store.add("B", mode="clone", payload={})
    p = DubTaskManagerPanel(AppState(), load_config(), store, None, None, lambda: None)
    seen = []
    p.taskSelected.connect(seen.append)
    p.table.setCurrentCell(0, 0)
    assert seen and seen[-1].id == store.all()[0].id
    assert hasattr(p, "taskDeleted")
