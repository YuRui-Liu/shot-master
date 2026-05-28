import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.app_shell import AppShell


def _app():
    return QApplication.instance() or QApplication([])


def test_soundtrack_page_is_task_workspace():
    _app()
    from drama_shot_master.ui.pages.task_workspace_page import TaskWorkspacePage
    from drama_shot_master.ui.panels.soundtrack_panel import SoundtrackPanel
    w = AppShell()
    page = w.pages["soundtrack"]
    assert isinstance(page, TaskWorkspacePage)
    assert isinstance(page.manager, SoundtrackPanel)
    assert w._soundtrack_panel() is page.manager


def test_soundtrack_select_creates_editor_inline():
    _app()
    from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor
    w = AppShell()
    page = w.pages["soundtrack"]; m = page.manager
    tasks = m.cfg.soundtrack_tasks
    if not tasks:
        m._on_new()
    else:
        m._select_task(tasks[0]["id"])
    tid = m.cfg.soundtrack_tasks[0]["id"]
    assert isinstance(page._editors[tid], SoundtrackEditor)


def test_soundtrack_dirty_writes_back_to_cfg():
    _app()
    w = AppShell()
    if not w.cfg.soundtrack_tasks:
        w.cfg.soundtrack_tasks.append(
            {"id": "tz", "name": "Z", "mp4": "", "style": "", "status": "空闲", "output": ""})
    tid = w.cfg.soundtrack_tasks[0]["id"]
    w._on_soundtrack_dirty(tid, {"mp4": "/a.mp4", "style": "暗黑", "output_dir": "/o"})
    t = next(t for t in w.cfg.soundtrack_tasks if t["id"] == tid)
    assert t["mp4"] == "/a.mp4" and t["style"] == "暗黑" and t["output_dir"] == "/o"
