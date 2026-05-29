"""UndoStack：push 自动 execute + undo/redo + MAX_DEPTH 截断 + signals."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.daw.undo_stack import UndoStack


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _FakeCmd:
    """最简 Command 不依赖真 commands.py。"""
    def __init__(self, log, name):
        self.log = log
        self.name = name

    def execute(self):
        self.log.append(f"exec:{self.name}")

    def undo(self):
        self.log.append(f"undo:{self.name}")

    def redo(self):
        self.log.append(f"redo:{self.name}")


def test_push_executes_and_marks_can_undo(app):
    stk = UndoStack()
    log = []
    stk.push(_FakeCmd(log, "A"))
    assert log == ["exec:A"]
    assert stk.can_undo() is True
    assert stk.can_redo() is False


def test_undo_redo_cycle(app):
    stk = UndoStack()
    log = []
    stk.push(_FakeCmd(log, "A"))
    stk.undo()
    assert log == ["exec:A", "undo:A"]
    assert stk.can_undo() is False and stk.can_redo() is True
    stk.redo()
    assert log == ["exec:A", "undo:A", "redo:A"]


def test_push_clears_redo_stack(app):
    stk = UndoStack()
    log = []
    stk.push(_FakeCmd(log, "A"))
    stk.undo()
    assert stk.can_redo() is True
    stk.push(_FakeCmd(log, "B"))
    assert stk.can_redo() is False


def test_max_depth_truncates_oldest(app):
    stk = UndoStack()
    stk.MAX_DEPTH = 3
    log = []
    for i in range(5):
        stk.push(_FakeCmd(log, str(i)))
    # 应保留最后 3 条 (2/3/4)
    for _ in range(3):
        stk.undo()
    assert log[-3:] == ["undo:4", "undo:3", "undo:2"]
    assert stk.can_undo() is False


def test_clear(app):
    stk = UndoStack()
    log = []
    stk.push(_FakeCmd(log, "A"))
    stk.push(_FakeCmd(log, "B"))
    stk.clear()
    assert stk.can_undo() is False and stk.can_redo() is False


def test_signals_emitted(app):
    stk = UndoStack()
    can_undo_events, can_redo_events = [], []
    stk.canUndoChanged.connect(can_undo_events.append)
    stk.canRedoChanged.connect(can_redo_events.append)
    log = []
    stk.push(_FakeCmd(log, "A"))
    assert can_undo_events[-1] is True
    stk.undo()
    assert can_undo_events[-1] is False
    assert can_redo_events[-1] is True
