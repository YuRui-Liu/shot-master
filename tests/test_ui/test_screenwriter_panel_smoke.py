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
    # 单视图：去掉任务栏后无 _task_manager / _task_bar
    assert not hasattr(panel, "_task_manager")
    assert not hasattr(panel, "_task_bar")
    assert hasattr(panel, "_wizard_host")
    assert panel._wizard_host._stack.count() == 6   # 6 阶段（Stage5 视频提示词 + Stage6 配音配乐）


def test_panel_set_project_api():
    _app()
    panel = ScreenwriterPanel(_Cfg())
    # 无项目时注入 None 应安全（全 page set_project(None)）
    assert panel.set_project(None) is True
