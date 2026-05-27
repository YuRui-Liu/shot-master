import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.app_shell import AppShell


def _app():
    return QApplication.instance() or QApplication([])


def test_shell_constructs_and_registers_seven_pages():
    _app()
    w = AppShell()
    w.show(); QApplication.instance().processEvents()
    assert len(w.pages) == 7


def test_shell_breadcrumb_reflects_initial_function():
    _app()
    w = AppShell()
    txt = w.breadcrumb_text()
    assert "›" in txt
