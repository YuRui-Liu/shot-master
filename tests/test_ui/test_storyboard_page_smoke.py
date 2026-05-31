"""StoryboardPage（分镜板合并页，纯容器）smoke 测试。

本页只做容器：顶部 QTabWidget，4 个 tab（出图/拆图/拼图/裁边）。
不构造具体 panel——Wave2 由 app_shell 构造后传入。
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget


def _app():
    return QApplication.instance() or QApplication([])


def _fake_items():
    # (key, label, widget) —— 用 4 个假 QWidget 占位
    return [
        ("imggen", "出图", QWidget()),
        ("split", "拆图", QWidget()),
        ("stitch", "拼图", QWidget()),
        ("trim", "裁边", QWidget()),
    ]


def test_set_tabs_creates_four_tabs_with_titles():
    _app()
    from drama_shot_master.ui.pages.storyboard_page import StoryboardPage
    items = _fake_items()
    page = StoryboardPage()
    page.set_tabs(items)
    assert page.tabs.count() == 4
    assert [page.tabs.tabText(i) for i in range(4)] == ["出图", "拆图", "拼图", "裁边"]


def test_tabs_hold_passed_widgets():
    _app()
    from drama_shot_master.ui.pages.storyboard_page import StoryboardPage
    items = _fake_items()
    page = StoryboardPage()
    page.set_tabs(items)
    for i, (_key, _label, w) in enumerate(items):
        assert page.tabs.widget(i) is w


def test_default_current_is_first_imggen():
    _app()
    from drama_shot_master.ui.pages.storyboard_page import StoryboardPage
    page = StoryboardPage()
    page.set_tabs(_fake_items())
    # 默认第 0 个（出图）
    assert page.tabs.currentIndex() == 0
    assert page.current_key() == "imggen"


def test_current_key_changes_on_switch():
    _app()
    from drama_shot_master.ui.pages.storyboard_page import StoryboardPage
    page = StoryboardPage()
    page.set_tabs(_fake_items())
    page.tabs.setCurrentIndex(2)
    assert page.current_key() == "stitch"
    page.tabs.setCurrentIndex(3)
    assert page.current_key() == "trim"


def test_set_tabs_via_constructor():
    _app()
    from drama_shot_master.ui.pages.storyboard_page import StoryboardPage
    items = _fake_items()
    page = StoryboardPage(items)
    assert page.tabs.count() == 4
    assert page.current_key() == "imggen"
