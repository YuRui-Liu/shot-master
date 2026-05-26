import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.windows.soundtrack_task_window import (
    SoundtrackTaskWindow, DEFAULT_WORKFLOW_ID)


def _app():
    return QApplication.instance() or QApplication([])


def test_window_constructs_with_task_defaults():
    _app()
    task = {"id": "t1", "name": "EP01", "mp4": "/x/ep1.mp4",
            "style": "末日废土", "workflow_id": "", "status": "空闲", "output": ""}
    win = SoundtrackTaskWindow(task, cfg=type("C", (), {})(), work_root="/tmp/stk")
    assert win.task_id == "t1"
    assert win.style_edit.toPlainText() == "末日废土"
    assert win.mp4_edit.text() == "/x/ep1.mp4"
    assert win.workflow_edit.text() == DEFAULT_WORKFLOW_ID


def test_window_emits_closed_on_close():
    _app()
    task = {"id": "t9", "name": "EP09", "mp4": "", "style": "x",
            "workflow_id": "", "status": "空闲", "output": ""}
    win = SoundtrackTaskWindow(task, cfg=type("C", (), {})(), work_root="/tmp/stk")
    seen = []
    win.closed.connect(seen.append)
    win.close()
    assert seen == ["t9"]               # 关窗发 closed(task_id)，供 main_window 清引用
