import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QMainWindow
from drama_shot_master.ui.theme import apply_window_icon, _find_app_icon_path


def _app():
    return QApplication.instance() or QApplication([])


def test_find_app_icon_path_exists():
    p = _find_app_icon_path()
    assert p is not None and p.exists()


def test_apply_window_icon_sets_nonnull_icon():
    _app()
    w = QMainWindow()
    assert w.windowIcon().isNull()
    apply_window_icon(w)
    assert not w.windowIcon().isNull()
