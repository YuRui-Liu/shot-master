import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QWidget, QTabWidget
from drama_shot_master.ui.pages.video_post_page import VideoPostPage


def _app():
    return QApplication.instance() or QApplication([])


def _items():
    # (key, 标题, widget)：用假 QWidget，本页只做容器不构造具体 panel
    return [
        ("dub", "配音", QWidget()),
        ("soundtrack", "配乐", QWidget()),
    ]


def test_page_is_tab_container():
    _app()
    page = VideoPostPage()
    assert isinstance(page.tabs, QTabWidget)


def test_set_tabs_adds_two_tabs():
    _app()
    page = VideoPostPage()
    page.set_tabs(_items())
    assert page.tabs.count() == 2
    assert page.tabs.tabText(0) == "配音"
    # 配乐 tab 标题带「项目级」小标注
    assert "配乐" in page.tabs.tabText(1)
    assert "项目级" in page.tabs.tabText(1)


def test_tabs_hold_given_widgets():
    _app()
    page = VideoPostPage()
    items = _items()
    page.set_tabs(items)
    assert page.tabs.widget(0) is items[0][2]
    assert page.tabs.widget(1) is items[1][2]


def test_current_key_reflects_active_tab():
    _app()
    page = VideoPostPage()
    page.set_tabs(_items())
    assert page.current_key() == "dub"
    page.tabs.setCurrentIndex(1)
    assert page.current_key() == "soundtrack"


def test_set_tabs_is_idempotent():
    _app()
    page = VideoPostPage()
    page.set_tabs(_items())
    page.set_tabs(_items())
    assert page.tabs.count() == 2
