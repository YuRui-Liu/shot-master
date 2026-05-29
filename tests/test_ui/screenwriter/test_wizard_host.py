"""ScreenwriterWizardHost 测试。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget, QLabel

from drama_shot_master.ui.widgets.screenwriter.wizard_host import ScreenwriterWizardHost


def _app():
    return QApplication.instance() or QApplication([])


def test_host_builds_with_4_pages():
    _app()
    pages = [QLabel(f"P{i}") for i in range(4)]
    host = ScreenwriterWizardHost(pages, stage_names=["创意", "剧本", "分镜", "提示词"])
    assert host._stack.count() == 4


def test_stage_button_switches_stack():
    _app()
    pages = [QLabel(f"P{i}") for i in range(4)]
    host = ScreenwriterWizardHost(pages, stage_names=["创意", "剧本", "分镜", "提示词"])
    host.set_stage(2)
    assert host._stack.currentIndex() == 2


def test_invalid_stage_index_clamped():
    _app()
    pages = [QLabel(f"P{i}") for i in range(4)]
    host = ScreenwriterWizardHost(pages, stage_names=["a", "b", "c", "d"])
    host.set_stage(99)
    assert host._stack.currentIndex() in (3, 0)   # 不崩
