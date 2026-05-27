import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.flow_sidebar import FlowSidebar, COLLAPSED_W, EXPANDED_W
from drama_shot_master.ui.nav_config import FUNCS, PHASES


def _app():
    return QApplication.instance() or QApplication([])


def test_renders_all_functions_and_phase_headers():
    _app()
    sb = FlowSidebar()
    assert set(sb._buttons.keys()) == {k for _l, k in FUNCS}
    assert len(sb._phase_labels) == len(PHASES)


def test_clicking_item_emits_currentChanged_key():
    _app()
    sb = FlowSidebar()
    seen = []
    sb.currentChanged.connect(seen.append)
    sb._buttons["video_gen"].click()
    assert seen == ["video_gen"]


def test_set_active_checks_button():
    _app()
    sb = FlowSidebar()
    sb.set_active("trim")
    assert sb._buttons["trim"].isChecked()


def test_collapse_switches_icononly_and_width():
    _app()
    sb = FlowSidebar()
    assert sb.minimumWidth() == EXPANDED_W
    sb.set_collapsed(True)
    assert sb.is_collapsed
    assert sb._buttons["split"].toolButtonStyle() == Qt.ToolButtonIconOnly
    assert sb.minimumWidth() == COLLAPSED_W
    sb.set_collapsed(False)
    assert sb._buttons["split"].toolButtonStyle() == Qt.ToolButtonTextBesideIcon
    assert sb.minimumWidth() == EXPANDED_W


def test_settings_and_help_signals():
    _app()
    sb = FlowSidebar()
    s, h = [], []
    sb.settingsRequested.connect(lambda: s.append(1))
    sb.helpRequested.connect(lambda: h.append(1))
    sb.btn_settings.click(); sb.btn_help.click()
    assert s == [1] and h == [1]
