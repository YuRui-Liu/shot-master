import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.flow_sidebar import FlowSidebar, COLLAPSED_W, EXPANDED_W
from drama_shot_master.ui.nav_config import NAV_ITEMS


def _app():
    return QApplication.instance() or QApplication([])


def test_renders_all_flat_nav_items_no_phase_headers():
    """Wave2a：扁平渲染——按钮 = NAV_ITEMS 全部 nav_key（含概览），无阶段 header。"""
    _app()
    sb = FlowSidebar()
    assert set(sb._buttons.keys()) == {k for _l, k in NAV_ITEMS}
    # 不再渲染阶段分组 header QLabel
    assert sb._phase_labels == []


def test_clicking_item_emits_currentChanged_key():
    _app()
    sb = FlowSidebar()
    seen = []
    sb.currentChanged.connect(seen.append)
    sb._buttons["video_gen"].click()
    assert seen == ["video_gen"]


def test_clicking_overview_emits_overview():
    _app()
    sb = FlowSidebar()
    seen = []
    sb.currentChanged.connect(seen.append)
    sb._buttons["overview"].click()
    assert seen == ["overview"]


def test_set_active_checks_button():
    _app()
    sb = FlowSidebar()
    sb.set_active("storyboard")
    assert sb._buttons["storyboard"].isChecked()


def test_collapse_switches_icononly_and_width():
    _app()
    sb = FlowSidebar()
    assert sb.minimumWidth() == EXPANDED_W
    sb.set_collapsed(True)
    assert sb.is_collapsed
    assert sb._buttons["storyboard"].toolButtonStyle() == Qt.ToolButtonIconOnly
    assert sb.minimumWidth() == COLLAPSED_W
    sb.set_collapsed(False)
    assert sb._buttons["storyboard"].toolButtonStyle() == Qt.ToolButtonTextBesideIcon
    assert sb.minimumWidth() == EXPANDED_W


def test_settings_and_help_signals():
    _app()
    sb = FlowSidebar()
    s, h = [], []
    sb.settingsRequested.connect(lambda: s.append(1))
    sb.helpRequested.connect(lambda: h.append(1))
    sb.btn_settings.click(); sb.btn_help.click()
    assert s == [1] and h == [1]
