import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QWidget, QStackedWidget, QMainWindow
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


def test_central_widget_shown_after_reparent_from_stack():
    """回归：从 QStackedWidget 浮出的编辑器被 Qt reparent 隐藏；
    DetachedEditorWindow 须保证其可见（否则窗内空白）。"""
    _app()
    ed = QWidget()
    stack = QStackedWidget()
    stack.addWidget(ed)
    stack.setCurrentWidget(ed)
    host = QMainWindow()
    host.setCentralWidget(stack)
    host.show()
    QApplication.instance().processEvents()
    ed.setParent(None)              # 模拟 pop_out：Qt 会把 ed 标记为隐藏
    assert ed.isHidden()            # 前提成立
    win = DetachedEditorWindow(ed, "视频任务 · A", "t1")
    win.show()
    QApplication.instance().processEvents()
    assert win.centralWidget() is ed
    assert not ed.isHidden()        # 关键：内容可见，非空白


def test_size_param_applied():
    _app()
    win = DetachedEditorWindow(QWidget(), "T", "t1", size=(720, 780))
    assert win.width() == 720 and win.height() == 780
