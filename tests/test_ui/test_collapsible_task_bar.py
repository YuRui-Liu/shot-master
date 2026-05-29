"""CollapsibleTaskBar 组件测试。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


# ── Task 2: IconRailItem + _RailBadge ─────────────────────────────────────

def test_rail_badge_size():
    _app()
    from drama_shot_master.ui.widgets.collapsible_task_bar import IconRailItem, _RailBadge
    item = IconRailItem(1, "A", "idle", "tt", "x")
    badge = _RailBadge(item)
    assert badge.width() == 40 and badge.height() == 36


def test_rail_badge_emits_item_id_on_click():
    _app()
    from drama_shot_master.ui.widgets.collapsible_task_bar import IconRailItem, _RailBadge
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    item = IconRailItem(1, "测", "done", "测试项目\n已完成", "id-abc")
    badge = _RailBadge(item)
    got = []
    badge.clicked.connect(got.append)
    QTest.mouseClick(badge, Qt.LeftButton)
    assert got == ["id-abc"]


def test_rail_badge_all_status_keys_have_color():
    _app()
    from drama_shot_master.ui.widgets.collapsible_task_bar import _RailBadge
    for status in ("done", "running", "idle", "error"):
        color = _RailBadge.STATUS_COLORS[status]
        assert color.startswith("#") and len(color) == 7


# ── Task 3: _IconRail ──────────────────────────────────────────────────────

def test_icon_rail_badge_count():
    _app()
    from drama_shot_master.ui.widgets.collapsible_task_bar import IconRailItem, _IconRail
    rail = _IconRail()
    items = [IconRailItem(i + 1, "X", "idle", "t", f"id{i}") for i in range(3)]
    rail.refresh(items)
    assert rail.badge_count() == 3


def test_icon_rail_empty_shows_zero():
    _app()
    from drama_shot_master.ui.widgets.collapsible_task_bar import _IconRail
    rail = _IconRail()
    rail.refresh([])
    assert rail.badge_count() == 0


def test_icon_rail_item_clicked_forwarded():
    _app()
    from drama_shot_master.ui.widgets.collapsible_task_bar import IconRailItem, _IconRail, _RailBadge
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    rail = _IconRail()
    items = [IconRailItem(1, "A", "done", "tip", "my-id")]
    rail.refresh(items)
    got = []
    rail.item_clicked.connect(got.append)
    badges = rail.findChildren(_RailBadge)
    assert len(badges) == 1
    QTest.mouseClick(badges[0], Qt.LeftButton)
    assert got == ["my-id"]


def test_icon_rail_expand_clicked_signal():
    _app()
    from drama_shot_master.ui.widgets.collapsible_task_bar import _IconRail
    rail = _IconRail()
    got = []
    rail.expand_clicked.connect(lambda: got.append(True))
    rail._expand_btn.click()
    assert got == [True]
