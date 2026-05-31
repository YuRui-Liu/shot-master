"""nav_config.PHASE_GATES 门禁元数据单测（Qt-free 纯逻辑）。

校验：8 功能 ↔ 4 阶段标题 ↔ manifest.STAGE_NAMES 三方显式映射自洽：
  - 每个 func_key 映射到合法 STAGE_NAMES；
  - 4 阶段都有功能挂载；
  - phase_of / stage_of / gated_funcs 自洽（互为反查）。
不依赖 Qt，不碰 tests/test_ui/test_nav_config.py。
"""
from __future__ import annotations

from drama_shot_master.core.compass.manifest import STAGE_NAMES
from drama_shot_master.ui import nav_config as nc


def test_every_func_key_gated_to_valid_stage():
    """每个 FUNCS 里的 func_key 都在 PHASE_GATES，且映射到合法 STAGE_NAMES。"""
    func_keys = {key for _label, key in nc.FUNCS}
    for key in func_keys:
        assert key in nc.PHASE_GATES, f"{key} 缺门禁映射"
        assert nc.PHASE_GATES[key] in STAGE_NAMES, (
            f"{key}→{nc.PHASE_GATES[key]} 非法阶段"
        )


def test_phase_gates_only_covers_known_func_keys():
    """PHASE_GATES 的 key 不引入 FUNCS 之外的功能。"""
    func_keys = {key for _label, key in nc.FUNCS}
    assert set(nc.PHASE_GATES) == func_keys


def test_all_four_stages_have_funcs():
    """4 个阶段（STAGE_NAMES）每个都至少挂 1 个功能。"""
    covered = set(nc.PHASE_GATES.values())
    assert covered == set(STAGE_NAMES)
    for stage in STAGE_NAMES:
        assert nc.gated_funcs(stage), f"阶段 {stage} 无功能"


def test_stage_of_matches_phase_gates():
    """stage_of(func_key) 与 PHASE_GATES 一致。"""
    for _label, key in nc.FUNCS:
        assert nc.stage_of(key) == nc.PHASE_GATES[key]


def test_stage_of_unknown_returns_none():
    """未知 func_key → None（不抛）。"""
    assert nc.stage_of("__nope__") is None


def test_phase_of_returns_phase_title():
    """phase_of(func_key) 返回该功能所属 PHASES 阶段标题（中文 emoji）。"""
    phase_titles = {title for title, _keys in nc.PHASES}
    for _label, key in nc.FUNCS:
        title = nc.phase_of(key)
        assert title in phase_titles, f"{key}→{title} 非法标题"
    assert nc.phase_of("__nope__") is None


def test_phase_of_consistent_with_phases_grouping():
    """phase_of 与 PHASES 原始分组一致。"""
    for title, keys in nc.PHASES:
        for key in keys:
            assert nc.phase_of(key) == title


def test_gated_funcs_is_inverse_of_stage_of():
    """gated_funcs(stage) 列出的功能，stage_of 都回指该 stage。"""
    for stage in STAGE_NAMES:
        for key in nc.gated_funcs(stage):
            assert nc.stage_of(key) == stage


def test_gated_funcs_unknown_stage_empty():
    """未知阶段 → 空列表（不抛）。"""
    assert nc.gated_funcs("__nope__") == []


def test_gated_funcs_partition_covers_all_funcs():
    """所有阶段的 gated_funcs 并集 = 全部 func_key（完整划分、无遗漏无重复）。"""
    func_keys = {key for _label, key in nc.FUNCS}
    union: list[str] = []
    for stage in STAGE_NAMES:
        union.extend(nc.gated_funcs(stage))
    assert sorted(union) == sorted(func_keys)
    assert len(union) == len(set(union)), "功能在多个阶段重复挂载"


# ====================================================================== #
# Wave2a 扁平导航门禁（NAV_ITEMS / NAV_STAGE / nav_gated）
# ====================================================================== #

def test_nav_items_order_and_keys():
    """扁平导航 6 项、顺序与键确定（概览置顶）。"""
    keys = [k for _l, k in nc.NAV_ITEMS]
    assert keys == [
        "overview", "screenwriter", "asset_library",
        "storyboard", "video_gen", "video_post",
    ]


def test_overview_not_gated():
    """概览不门禁：不在 NAV_STAGE 内，stage_of 返回 None。"""
    assert "overview" not in nc.NAV_STAGE
    assert nc.stage_of("overview") is None


def test_nav_stage_maps_to_valid_stage_names():
    """除概览外每个 nav_key 都映射到合法 STAGE_NAMES。"""
    nav_keys = {k for _l, k in nc.NAV_ITEMS if k != "overview"}
    assert set(nc.NAV_STAGE) == nav_keys
    for k, stage in nc.NAV_STAGE.items():
        assert stage in STAGE_NAMES, f"{k}→{stage} 非法阶段"


def test_video_gen_and_post_share_production():
    """视频生成 / 视频后期 同属 production 阶段。"""
    assert nc.NAV_STAGE["video_gen"] == "production"
    assert nc.NAV_STAGE["video_post"] == "production"


def test_stage_of_prefers_nav_key():
    """stage_of 对扁平 nav_key 优先查 NAV_STAGE。"""
    assert nc.stage_of("asset_library") == "assets"
    assert nc.stage_of("video_post") == "production"


def test_nav_gated_production_has_two_navs():
    """nav_gated(production) 返回 video_gen + video_post 两个 nav_key（按序）。"""
    assert nc.nav_gated("production") == ["video_gen", "video_post"]
    assert nc.nav_gated("assets") == ["asset_library"]
    assert nc.nav_gated("__nope__") == []


def test_storyboard_and_videopost_tabs():
    """容器页 tab 定义：分镜板 4 tab、视频后期 3 tab（成片在首），key 为真实底层 panel。"""
    sb_keys = [k for k, _l in nc.STORYBOARD_TABS]
    assert sb_keys == ["imggen", "split", "combine", "trim"]
    vp_keys = [k for k, _l in nc.VIDEOPOST_TABS]
    assert vp_keys == ["compose", "dubbing", "soundtrack"]
