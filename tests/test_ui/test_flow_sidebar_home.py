import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


def test_flow_sidebar_has_home_requested_signal():
    _app()
    from drama_shot_master.ui.widgets.flow_sidebar import FlowSidebar
    sidebar = FlowSidebar()
    assert hasattr(sidebar, "homeRequested")
    assert hasattr(sidebar, "btn_home")


def test_flow_sidebar_home_button_emits():
    _app()
    from drama_shot_master.ui.widgets.flow_sidebar import FlowSidebar
    sidebar = FlowSidebar()
    got = []
    sidebar.homeRequested.connect(lambda: got.append(True))
    sidebar.btn_home.click()
    assert got == [True]
