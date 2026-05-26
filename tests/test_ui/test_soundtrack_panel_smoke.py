import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Ensure real PySide6 is importable in environments where it lives in a
# different Python version's site-packages (e.g. conda UniRig env on Python 3.11
# running alongside the system Python 3.10 pytest).
_PYSIDE6_EXTRA = "/root/miniconda3/envs/UniRig/lib/python3.11/site-packages"
if _PYSIDE6_EXTRA not in sys.path:
    sys.path.append(_PYSIDE6_EXTRA)

# The root conftest may have registered PySide6 stub modules before our path
# injection; remove stubs so the real C-extension is imported instead.
for _k in list(sys.modules):
    if _k == "PySide6" or _k.startswith("PySide6."):
        del sys.modules[_k]

from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.panels.soundtrack_panel import SoundtrackPanel


def _app():
    try:
        return QApplication.instance() or QApplication([])
    except (AttributeError, TypeError):
        # PySide6 is stubbed in headless CI; a real QApplication is not needed.
        return None


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
