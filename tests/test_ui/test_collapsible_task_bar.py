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


# ── Task 4: CollapsibleTaskBar ────────────────────────────────────────────

from PySide6.QtWidgets import QWidget as _QWidget


class _StubManager(_QWidget):
    """最小桩：实现 icon_rail_items() 协议。"""
    from PySide6.QtCore import Signal as _Signal
    icon_rail_updated = _Signal()

    def icon_rail_items(self):
        return []


def test_collapse_changes_splitter_sizes():
    _app()
    from PySide6.QtWidgets import QSplitter, QWidget
    from drama_shot_master.ui.widgets.collapsible_task_bar import CollapsibleTaskBar
    stub = _StubManager()
    right = QWidget()
    splitter = QSplitter()
    bar = CollapsibleTaskBar(stub, splitter, manager_index=0, expanded_width=280)
    splitter.addWidget(bar)
    splitter.addWidget(right)
    splitter.resize(800, 600)
    splitter.setSizes([280, 520])
    bar.collapse()
    assert splitter.sizes()[0] == 40


def test_expand_restores_width():
    _app()
    from PySide6.QtWidgets import QSplitter, QWidget
    from drama_shot_master.ui.widgets.collapsible_task_bar import CollapsibleTaskBar
    stub = _StubManager()
    right = QWidget()
    splitter = QSplitter()
    bar = CollapsibleTaskBar(stub, splitter, manager_index=0, expanded_width=280)
    splitter.addWidget(bar)
    splitter.addWidget(right)
    splitter.resize(800, 600)
    splitter.setSizes([280, 520])
    bar.collapse()
    bar.expand()
    assert splitter.sizes()[0] == 280


def test_is_collapsed_state():
    _app()
    from PySide6.QtWidgets import QSplitter, QWidget
    from drama_shot_master.ui.widgets.collapsible_task_bar import CollapsibleTaskBar
    stub = _StubManager()
    right = QWidget()
    splitter = QSplitter()
    bar = CollapsibleTaskBar(stub, splitter, manager_index=0)
    splitter.addWidget(bar)
    splitter.addWidget(right)
    splitter.resize(800, 600)
    splitter.setSizes([280, 520])
    assert bar.is_collapsed() is False
    bar.collapse()
    assert bar.is_collapsed() is True
    bar.expand()
    assert bar.is_collapsed() is False


def test_collapse_emits_signal():
    _app()
    from PySide6.QtWidgets import QSplitter, QWidget
    from drama_shot_master.ui.widgets.collapsible_task_bar import CollapsibleTaskBar
    stub = _StubManager()
    right = QWidget()
    splitter = QSplitter()
    bar = CollapsibleTaskBar(stub, splitter, manager_index=0)
    splitter.addWidget(bar)
    splitter.addWidget(right)
    splitter.resize(800, 600)
    splitter.setSizes([280, 520])
    got = []
    bar.collapsed.connect(lambda: got.append("collapsed"))
    bar.expanded.connect(lambda: got.append("expanded"))
    bar.collapse()
    bar.expand()
    assert got == ["collapsed", "expanded"]


def test_toggle_switches_state():
    _app()
    from PySide6.QtWidgets import QSplitter, QWidget
    from drama_shot_master.ui.widgets.collapsible_task_bar import CollapsibleTaskBar
    stub = _StubManager()
    right = QWidget()
    splitter = QSplitter()
    bar = CollapsibleTaskBar(stub, splitter, manager_index=0)
    splitter.addWidget(bar)
    splitter.addWidget(right)
    splitter.resize(800, 600)
    splitter.setSizes([280, 520])
    assert not bar.is_collapsed()
    bar.toggle()
    assert bar.is_collapsed()
    bar.toggle()
    assert not bar.is_collapsed()
