# tests/test_ui/test_welcome_registry_source.py
"""R2-5 阶段B（兼容扩展）· WelcomePage/ProjectCard 接 registry 数据源。

红线：阶段B 纯新增/数据源切换——
- 默认行为不变（不传 registry 时仍走 recent_mgr.load()）；
- registry 有项目 → refresh 渲染 registry 数据（含 project_id）；
- registry 空/不可用 → 降级回 recent_mgr.load()（双轨过渡）；
- ProjectCard 缺 project_id 不崩。

widget smoke 风格参考现有 tests/test_ui（QApplication offscreen）。
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


# ── ProjectCard 缺 project_id 不崩 ───────────────────────────────────────────

def test_project_card_without_project_id_does_not_crash():
    """旧数据无 project_id 字段 → 构造/绘制不崩，且 project_id() 返回 None。"""
    _app()
    from drama_shot_master.ui.widgets.project_card import ProjectCard
    card = ProjectCard({"name": "Old", "path": "/old", "last_opened": "", "shot_count": 0})
    card.show()
    # 缺字段不报错
    assert card.project_id() is None


def test_project_card_carries_project_id_when_present():
    """带 project_id 的数据 → ProjectCard.project_id() 透出该值。"""
    _app()
    from drama_shot_master.ui.widgets.project_card import ProjectCard
    card = ProjectCard(
        {"name": "New", "path": "/new", "last_opened": "", "shot_count": 0,
         "project_id": "P-007"}
    )
    assert card.project_id() == "P-007"


# ── WelcomePage 数据源：registry 优先 ────────────────────────────────────────

def test_refresh_uses_registry_when_available(tmp_path):
    """registry 有项目 → refresh 渲染 registry 数据（卡片携带 project_id）。"""
    _app()
    from drama_shot_master.core.recent_projects import RecentProjectsManager
    from drama_shot_master.core.compass.registry import ProjectRegistry
    from drama_shot_master.ui.pages.welcome_page import WelcomePage
    from drama_shot_master.ui.widgets.project_card import ProjectCard

    proj_dir = tmp_path / "proj_a"
    proj_dir.mkdir()

    reg = ProjectRegistry(tmp_path)
    pid = reg.allocate_id()
    reg.register({
        "project_id": pid,
        "project_name": "替嫁新娘的逆袭",
        "path": str(proj_dir),
        "episode_count": 12,
    })

    mgr = RecentProjectsManager(tmp_path / "r.json")  # 故意留空
    page = WelcomePage(mgr, registry=reg)
    page.refresh()

    proj_cards = [c for c in page._cards if isinstance(c, ProjectCard) and not c._is_add]
    assert len(proj_cards) == 1
    assert proj_cards[0].project_id() == pid


def test_refresh_falls_back_to_recent_when_registry_empty(tmp_path):
    """registry 空 → 降级回 recent_mgr.load()（双轨过渡）。"""
    _app()
    from drama_shot_master.core.recent_projects import RecentProjectsManager
    from drama_shot_master.core.compass.registry import ProjectRegistry
    from drama_shot_master.ui.pages.welcome_page import WelcomePage
    from drama_shot_master.ui.widgets.project_card import ProjectCard

    reg = ProjectRegistry(tmp_path)  # 空注册表

    proj_dir = tmp_path / "recent_only"
    proj_dir.mkdir()
    mgr = RecentProjectsManager(tmp_path / "r.json")
    mgr.push(str(proj_dir), "RecentProj")

    page = WelcomePage(mgr, registry=reg)
    page.refresh()

    proj_cards = [c for c in page._cards if isinstance(c, ProjectCard) and not c._is_add]
    assert len(proj_cards) == 1
    # 降级数据来自 recent，无 project_id
    assert proj_cards[0].project_id() is None


def test_refresh_default_behavior_unchanged_without_registry(tmp_path):
    """不传 registry → 默认行为不变，仍走 recent_mgr.load()。"""
    _app()
    from drama_shot_master.core.recent_projects import RecentProjectsManager
    from drama_shot_master.ui.pages.welcome_page import WelcomePage
    from drama_shot_master.ui.widgets.project_card import ProjectCard

    proj_dir = tmp_path / "p0"
    proj_dir.mkdir()
    mgr = RecentProjectsManager(tmp_path / "r.json")
    mgr.push(str(proj_dir), "P0")

    page = WelcomePage(mgr)  # 不传 registry
    page.refresh()

    proj_cards = [c for c in page._cards if isinstance(c, ProjectCard) and not c._is_add]
    assert len(proj_cards) == 1
    assert proj_cards[0].project_id() is None
