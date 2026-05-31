import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.app_shell import AppShell


def _app():
    return QApplication.instance() or QApplication([])


def test_dub_page_is_task_workspace():
    _app()
    from drama_shot_master.ui.pages.task_workspace_page import TaskWorkspacePage
    from drama_shot_master.ui.panels.dub_task_manager_panel import DubTaskManagerPanel
    w = AppShell()
    page = w._func_pages["dubbing"]
    assert isinstance(page, TaskWorkspacePage)
    assert isinstance(page.manager, DubTaskManagerPanel)
    assert w._dub_manager() is page.manager


def test_dub_select_creates_editor_inline():
    _app()
    from drama_shot_master.ui.panels.dub_panel import DubPanel
    w = AppShell()
    page = w._func_pages["dubbing"]; m = page.manager
    if not m.store.all():
        m.store.add("T1", mode="clone", payload={}); m.refresh()
    t = m.store.all()[0]
    m.taskSelected.emit(t)
    assert isinstance(page._editors[t.id], DubPanel)
