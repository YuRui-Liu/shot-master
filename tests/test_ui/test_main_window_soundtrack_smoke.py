import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.main_window import MainWindow, FUNCS


def test_main_window_has_soundtrack_tab():
    app = QApplication.instance() or QApplication([])
    keys = [key for _label, key in FUNCS]
    assert "soundtrack" in keys
    w = MainWindow()
    w.show(); app.processEvents()
    assert len(w.panels) == len(FUNCS)


def test_main_window_has_soundtrack_settings_method():
    app = QApplication.instance() or QApplication([])
    from drama_shot_master.ui.main_window import MainWindow
    w = MainWindow()
    assert hasattr(w, "_open_soundtrack_settings")
