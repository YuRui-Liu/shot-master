import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.panels.screenwriter_panel import ScreenwriterPanel


def _app():
    return QApplication.instance() or QApplication([])


class _Cfg:
    screenwriter_projects = []
    screenwriter_project_root = ""
    screenwriter_agent_port = 18999


def test_panel_constructs():
    _app()
    panel = ScreenwriterPanel(_Cfg())
    assert hasattr(panel, "_task_manager")
    assert hasattr(panel, "_wizard_host")
    assert hasattr(panel, "_task_bar")
    assert panel._wizard_host._stack.count() == 6   # 6 阶段（Stage5 视频提示词 + Stage6 配音配乐）


def test_panel_table_cols():
    _app()
    panel = ScreenwriterPanel(_Cfg())
    hdr = panel._task_manager._table.horizontalHeaderItem
    assert hdr(0).text() == "名称"
    assert hdr(1).text() == "状态"
