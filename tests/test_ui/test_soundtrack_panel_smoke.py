import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.panels.soundtrack_panel import SoundtrackPanel


def _app():
    return QApplication.instance() or QApplication([])


def test_panel_constructs_and_lists_tasks():
    _app()
    opened = []
    panel = SoundtrackPanel(
        state=None,
        cfg=type("C", (), {"soundtrack_tasks": [
            {"id": "t1", "name": "EP01", "mp4": "/x/ep1.mp4",
             "style": "冷色调", "status": "空闲", "output": ""}]})(),
        open_window_cb=lambda t: opened.append(t),
        persist_cb=lambda: None,
    )
    assert panel.table.rowCount() == 1
    assert panel.select_mode() == "none"
    ok, _why = panel.validate()
    assert ok is False
