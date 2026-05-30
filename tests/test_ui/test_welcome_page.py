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
    from drama_shot_master.ui.widgets.project_card import ProjectCard
    far = ProjectCard({"name": "A", "path": "/a", "last_opened": "", "shot_count": 0}, depth="far")
    center = ProjectCard({"name": "B", "path": "/b", "last_opened": "", "shot_count": 0}, depth="center")
    far_effect = far.graphicsEffect()
    center_effect = center.graphicsEffect()
    assert far_effect is None or far_effect.opacity() < 0.6
    assert center_effect is None or center_effect.opacity() >= 0.99


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
