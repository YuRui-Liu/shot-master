import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.nav_config import FUNCS
from drama_shot_master.ui.app_shell import AppShell


def _app():
    return QApplication.instance() or QApplication([])


def test_soundtrack_function_registered():
    keys = [key for _label, key in FUNCS]
    assert "soundtrack" in keys


def test_appshell_registers_all_functions():
    app = _app()
    w = AppShell()
    w.show(); app.processEvents()
    # Wave2a：底层 8 个真实功能页存 _func_pages（self.pages 改为扁平 6 项导航）。
    assert len(w._func_pages) == len(FUNCS)
    assert set(w._func_pages.keys()) == {k for _l, k in FUNCS}
