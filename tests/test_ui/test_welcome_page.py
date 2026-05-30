# tests/test_ui/test_welcome_page.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


# ── ProjectCard ────────────────────────────────────────────────────────────

def test_project_card_emits_path_on_click():
    _app()
    from drama_shot_master.ui.widgets.project_card import ProjectCard
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    card = ProjectCard({"name": "TestProj", "path": "/some/path", "last_opened": "", "shot_count": 3})
    card.show()
    got = []
    card.clicked.connect(got.append)
    QTest.mouseClick(card, Qt.LeftButton)
    assert got == ["/some/path"]


def test_add_card_emits_empty_string_on_click():
    _app()
    from drama_shot_master.ui.widgets.project_card import ProjectCard
    card = ProjectCard(None, is_add_button=True)
    card.show()
    got = []
    card.clicked.connect(got.append)
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    QTest.mouseClick(card, Qt.LeftButton)
    assert got == [""]


def test_project_card_depth_opacity():
    _app()
    from PySide6.QtWidgets import QGraphicsOpacityEffect
    from drama_shot_master.ui.widgets.project_card import ProjectCard
    far = ProjectCard({"name": "A", "path": "/a", "last_opened": "", "shot_count": 0}, depth="far")
    center = ProjectCard({"name": "B", "path": "/b", "last_opened": "", "shot_count": 0}, depth="center")
    far_effect = far.graphicsEffect()
    center_effect = center.graphicsEffect()
    # 远卡降低不透明度形成景深
    assert isinstance(far_effect, QGraphicsOpacityEffect) and far_effect.opacity() < 0.6
    # 中心卡不降不透明度（挂蓝紫发光 DropShadow，而非 Opacity）
    assert not isinstance(center_effect, QGraphicsOpacityEffect)


def test_project_card_depth_height_ratio():
    _app()
    from drama_shot_master.ui.widgets.project_card import ProjectCard
    far = ProjectCard({"name": "A", "path": "/a", "last_opened": "", "shot_count": 0}, depth="far")
    center = ProjectCard({"name": "B", "path": "/b", "last_opened": "", "shot_count": 0}, depth="center")
    add = ProjectCard(None, depth="add", is_add_button=True)
    # 中心卡最高(1.0)，远卡与新建卡更矮 → 景深阶梯
    assert center.height_ratio() == 1.0
    assert far.height_ratio() < center.height_ratio()
    assert add.height_ratio() < far.height_ratio()


# ── WelcomePage ────────────────────────────────────────────────────────────

def test_welcome_page_instantiates(tmp_path):
    _app()
    from drama_shot_master.core.recent_projects import RecentProjectsManager
    from drama_shot_master.ui.pages.welcome_page import WelcomePage
    mgr = RecentProjectsManager(tmp_path / "r.json")
    page = WelcomePage(mgr)
    assert page is not None


def test_welcome_page_has_required_signals(tmp_path):
    _app()
    from drama_shot_master.core.recent_projects import RecentProjectsManager
    from drama_shot_master.ui.pages.welcome_page import WelcomePage
    mgr = RecentProjectsManager(tmp_path / "r.json")
    page = WelcomePage(mgr)
    for sig_name in ("project_selected", "new_project_requested",
                     "open_dir_requested", "settings_requested"):
        assert hasattr(page, sig_name), f"missing signal: {sig_name}"


def test_welcome_page_refresh_shows_empty_state(tmp_path):
    _app()
    from drama_shot_master.core.recent_projects import RecentProjectsManager
    from drama_shot_master.ui.pages.welcome_page import WelcomePage
    mgr = RecentProjectsManager(tmp_path / "r.json")
    page = WelcomePage(mgr)
    page.refresh()
    assert page._cards_layout.count() >= 1


def test_welcome_page_refresh_shows_projects(tmp_path):
    _app()
    from drama_shot_master.core.recent_projects import RecentProjectsManager
    from drama_shot_master.ui.pages.welcome_page import WelcomePage
    mgr = RecentProjectsManager(tmp_path / "r.json")
    mgr.push(str(tmp_path), "TestProj")
    page = WelcomePage(mgr)
    page.refresh()
    assert page._cards_layout.count() >= 2


def test_welcome_page_project_selected_signal(tmp_path):
    _app()
    from drama_shot_master.core.recent_projects import RecentProjectsManager
    from drama_shot_master.ui.pages.welcome_page import WelcomePage
    from drama_shot_master.ui.widgets.project_card import ProjectCard
    mgr = RecentProjectsManager(tmp_path / "r.json")
    mgr.push(str(tmp_path), "TestProj")
    page = WelcomePage(mgr)
    page.refresh()

    got = []
    page.project_selected.connect(got.append)

    for i in range(page._cards_layout.count()):
        w = page._cards_layout.itemAt(i).widget()
        if isinstance(w, ProjectCard) and not w._is_add:
            w.clicked.emit(str(tmp_path))
            break

    assert got == [str(tmp_path)]


def test_welcome_page_cards_have_staggered_heights(tmp_path):
    _app()
    from drama_shot_master.core.recent_projects import RecentProjectsManager
    from drama_shot_master.ui.pages.welcome_page import WelcomePage
    from drama_shot_master.ui.widgets.project_card import ProjectCard
    mgr = RecentProjectsManager(tmp_path / "r.json")
    for i in range(4):
        d = tmp_path / f"p{i}"
        d.mkdir()
        mgr.push(str(d), f"P{i}")
    page = WelcomePage(mgr)
    page.resize(1360, 800)
    page.refresh()
    page._apply_card_heights()
    heights = {}
    for i in range(page._cards_layout.count()):
        w = page._cards_layout.itemAt(i).widget()
        if isinstance(w, ProjectCard):
            heights[w._depth] = w.height()
    # 景深阶梯：center 最高 > near > far，且都被设成了固定高度（非 0）
    assert heights["center"] > heights["near"] > heights["far"] > 0


def test_welcome_page_cards_are_portrait_and_centered(tmp_path):
    _app()
    from drama_shot_master.core.recent_projects import RecentProjectsManager
    from drama_shot_master.ui.pages.welcome_page import WelcomePage
    from drama_shot_master.ui.widgets.project_card import ProjectCard
    mgr = RecentProjectsManager(tmp_path / "r.json")
    d = tmp_path / "p0"
    d.mkdir()
    mgr.push(str(d), "P0")
    page = WelcomePage(mgr)
    page.resize(1600, 980)
    page.refresh()
    page._relayout_cards()
    center = next(c for c in page._cards if c._depth == "center")
    # 竖向缩略图：宽 < 高（不再是撑满宽度的横向大块）
    assert center.width() < center.height()
    # 卡片组不铺满整宽 → 背景/光晕从两侧透出
    total = sum(c.width() for c in page._cards)
    assert total < page._cards_area.width() - 48
