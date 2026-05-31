"""OverviewPage 概览仪表盘 smoke 测试（offscreen QApplication）。

覆盖：STYLE BIBLE 卡风格名、5 阶段卡 state class、next-action banner、
点卡发 stageActivated、编辑发 styleBibleEditRequested、空/缺数据不崩。
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


def _manifest(with_bible=True):
    """构造：screenwriter completed / assets in_progress / 其余 pending。"""
    from drama_shot_master.core.compass.manifest import ProjectManifest, StageState
    m = ProjectManifest(project_name="替嫁新娘的逆袭", genre="短剧")
    m.pipeline["screenwriter"] = StageState(state="completed", next_action="")
    m.pipeline["assets"] = StageState(
        state="in_progress", next_action="补全 角色/场景/道具 参考图")
    m.pipeline["storyboard"] = StageState(state="pending")
    m.pipeline["production"] = StageState(state="pending")
    if with_bible:
        # ref 指向 visual_styles.json 里存在的 id
        m.style_bible = {"ref": "real/cinematic-warm-v1", "category": "real"}
    return m


# ── 构造与渲染 ────────────────────────────────────────────────────────────

def test_set_manifest_renders_without_crash():
    _app()
    from drama_shot_master.ui.pages.overview_page import OverviewPage
    page = OverviewPage()
    page.set_manifest(_manifest())


def test_style_bible_card_shows_style_name():
    _app()
    from drama_shot_master.ui.pages.overview_page import OverviewPage
    page = OverviewPage()
    page.set_manifest(_manifest())
    # STYLE BIBLE 卡应显示风格中文名「电影感暖调」
    assert "电影感暖调" in page.style_bible_text()


def test_style_bible_card_unset_shows_placeholder():
    _app()
    from drama_shot_master.ui.pages.overview_page import OverviewPage
    page = OverviewPage()
    page.set_manifest(_manifest(with_bible=False))
    assert "未设定" in page.style_bible_text()


def test_style_bible_edit_emits_signal():
    _app()
    from drama_shot_master.ui.pages.overview_page import OverviewPage
    page = OverviewPage()
    page.set_manifest(_manifest())
    got = []
    page.styleBibleEditRequested.connect(lambda: got.append(True))
    page._edit_btn.click()
    assert got == [True]


# ── 5 阶段卡 state ─────────────────────────────────────────────────────────

def test_stage_cards_count_is_five():
    _app()
    from drama_shot_master.ui.pages.overview_page import OverviewPage
    page = OverviewPage()
    page.set_manifest(_manifest())
    assert len(page.stage_cards()) == 5


def test_stage_card_states_match_pipeline():
    _app()
    from drama_shot_master.ui.pages.overview_page import OverviewPage
    page = OverviewPage()
    page.set_manifest(_manifest())
    cards = {c.stage_key: c for c in page.stage_cards()}
    # screenwriter completed → done class
    assert cards["screenwriter"].state_class() == "done"
    # assets in_progress → cur class
    assert cards["assets"].state_class() == "cur"
    # storyboard pending → locked class
    assert cards["storyboard"].state_class() == "locked"
    # production (视频生成 + 视频后期) pending → locked
    prod_cards = [c for c in page.stage_cards() if c.stage_key == "production"]
    assert len(prod_cards) == 2
    assert all(c.state_class() == "locked" for c in prod_cards)


def test_next_action_banner_shows_current_stage_action():
    _app()
    from drama_shot_master.ui.pages.overview_page import OverviewPage
    page = OverviewPage()
    page.set_manifest(_manifest())
    assert "补全 角色/场景/道具 参考图" in page.next_action_text()


# ── 点卡发信号 ────────────────────────────────────────────────────────────

def test_stage_card_click_emits_stage_activated():
    _app()
    from drama_shot_master.ui.pages.overview_page import OverviewPage
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    page = OverviewPage()
    page.set_manifest(_manifest())
    got = []
    page.stageActivated.connect(got.append)
    cards = {c.stage_key: c for c in page.stage_cards()}
    QTest.mouseClick(cards["assets"], Qt.LeftButton)
    assert got == ["assets"]


# ── 数据缺失兜底 ──────────────────────────────────────────────────────────

def test_empty_manifest_does_not_crash():
    _app()
    from drama_shot_master.ui.pages.overview_page import OverviewPage
    from drama_shot_master.core.compass.manifest import ProjectManifest
    page = OverviewPage()
    page.set_manifest(ProjectManifest())
    assert len(page.stage_cards()) == 5
    assert "未设定" in page.style_bible_text()


def test_set_manifest_none_does_not_crash():
    _app()
    from drama_shot_master.ui.pages.overview_page import OverviewPage
    page = OverviewPage()
    page.set_manifest(None)
    # 仍可渲染 5 张卡
    assert len(page.stage_cards()) == 5
