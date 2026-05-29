import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QApplication, QWidget
from drama_shot_master.ui.pages.task_workspace_page import TaskWorkspacePage
from drama_shot_master.ui.windows.detached_editor_window import DetachedEditorWindow


def _app():
    return QApplication.instance() or QApplication([])


class _Task:
    def __init__(self, tid, name): self.id = tid; self.name = name


class _FakeManager(QWidget):
    taskSelected = Signal(object)


class _FakeEditor(QWidget):
    def __init__(self): super().__init__(); self.payload = {"v": 1}


def _page(persist_spy=None):
    mgr = _FakeManager()
    made = {}
    def factory(task):
        ed = _FakeEditor(); made[task.id] = ed; return ed
    page = TaskWorkspacePage(
        manager=mgr,
        editor_factory=factory,
        wire_editor=lambda ed, task: None,
        payload_of=lambda ed: ed.payload,
        on_persist=(persist_spy or (lambda tid, p: None)),
        title_for=lambda task: f"视频任务 · {task.name}",
    )
    return page, mgr, made


def test_select_shows_cached_editor():
    _app()
    page, mgr, made = _page()
    a, b = _Task("a", "A"), _Task("b", "B")
    mgr.taskSelected.emit(a)
    assert page._editors["a"] is made["a"]
    assert page.stack.currentWidget() is made["a"]
    mgr.taskSelected.emit(b)
    assert set(page._editors) == {"a", "b"}
    assert page.stack.currentWidget() is made["b"]
    mgr.taskSelected.emit(a)
    assert page.stack.currentWidget() is made["a"]
    assert page._editors["a"] is made["a"]


def test_pop_out_reparents_and_dock_back_returns():
    _app()
    page, mgr, made = _page()
    a = _Task("a", "A")
    mgr.taskSelected.emit(a)
    page.pop_out()
    win = page._detached["a"]
    assert isinstance(win, DetachedEditorWindow)
    assert win.centralWidget() is made["a"]
    assert page.stack.currentWidget() is page._placeholder
    win.close()
    assert "a" not in page._detached
    assert made["a"] in [page.stack.widget(i) for i in range(page.stack.count())]


def test_select_detached_task_shows_placeholder():
    _app()
    page, mgr, made = _page()
    a, b = _Task("a", "A"), _Task("b", "B")
    mgr.taskSelected.emit(a); page.pop_out()
    mgr.taskSelected.emit(b)
    mgr.taskSelected.emit(a)
    assert page.stack.currentWidget() is page._placeholder


def test_flush_all_persists_every_editor():
    _app()
    calls = []
    page, mgr, made = _page(persist_spy=lambda tid, p: calls.append((tid, p)))
    mgr.taskSelected.emit(_Task("a", "A"))
    mgr.taskSelected.emit(_Task("b", "B"))
    calls.clear()
    page.flush_all()
    assert {tid for tid, _ in calls} == {"a", "b"}


def test_discard_current_editor_shows_placeholder():
    _app()
    page, mgr, made = _page()
    a = _Task("a", "A")
    mgr.taskSelected.emit(a)
    assert page.stack.currentWidget() is made["a"]
    page.discard_editor("a")
    assert "a" not in page._editors
    assert page.stack.currentWidget() is page._placeholder


def test_discard_detached_task_cleans_up():
    _app()
    page, mgr, made = _page()
    a = _Task("a", "A")
    mgr.taskSelected.emit(a)
    page.pop_out()
    assert "a" in page._detached
    page.discard_editor("a")
    assert "a" not in page._detached
    assert "a" not in page._editors
    # 不应崩；当前无任务 → 占位
    assert page.stack.currentWidget() is page._placeholder


def test_update_task_name_updates_inline_header():
    _app()
    page, mgr, made = _page()
    a = _Task("a", "A")
    mgr.taskSelected.emit(a)
    page.update_task_name("a", "新名字")
    assert page.lbl_task.text() == "新名字"


def test_pop_out_editor_is_shown_not_blank():
    """回归：浮出后编辑器被 reparent 隐藏会导致窗内空白；须可见。"""
    _app()
    page, mgr, made = _page()
    a = _Task("a", "A")
    mgr.taskSelected.emit(a)
    ed = made["a"]
    page.pop_out()
    QApplication.instance().processEvents()
    win = page._detached["a"]
    assert win.centralWidget() is ed
    assert not ed.isHidden()        # 非空白


def test_detached_size_threaded_to_window():
    _app()
    page, mgr, made = _page()
    page._detached_size = (720, 780)
    a = _Task("a", "A")
    mgr.taskSelected.emit(a)
    page.pop_out()
    win = page._detached["a"]
    assert (win.width(), win.height()) == (720, 780)


def test_task_workspace_has_collapsible_bar():
    _app()
    from drama_shot_master.ui.pages.task_workspace_page import TaskWorkspacePage
    from drama_shot_master.ui.widgets.collapsible_task_bar import CollapsibleTaskBar

    class _ManagerWithRail(_FakeManager):
        from PySide6.QtCore import Signal as _Signal
        icon_rail_updated = _Signal()
        def icon_rail_items(self): return []

    mgr = _ManagerWithRail()
    page = TaskWorkspacePage(
        manager=mgr,
        editor_factory=lambda task: _FakeEditor(),
        wire_editor=lambda ed, task: None,
        payload_of=lambda ed: ed.payload,
        on_persist=lambda tid, p: None,
        title_for=lambda task: f"任务 · {task.name}",
    )
    assert hasattr(page, "_task_bar")
    assert isinstance(page._task_bar, CollapsibleTaskBar)
