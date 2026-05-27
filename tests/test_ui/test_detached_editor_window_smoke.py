import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QWidget
from drama_shot_master.ui.windows.detached_editor_window import DetachedEditorWindow


def _app():
    return QApplication.instance() or QApplication([])


def test_hosts_editor_and_emits_closed_without_deleting_editor():
    _app()
    ed = QWidget()
    win = DetachedEditorWindow(ed, "视频任务 · A", "t1")
    assert win.centralWidget() is ed
    seen = []
    win.closed.connect(seen.append)
    win.close()
    assert seen == ["t1"]
    # editor 仍存活（未被窗销毁）——可被重新 setParent
    ed.setParent(None)
    assert ed is not None


def test_set_title():
    _app()
    win = DetachedEditorWindow(QWidget(), "视频任务 · A", "t1")
    win.set_title("视频任务 · B")
    assert "B" in win.windowTitle()
