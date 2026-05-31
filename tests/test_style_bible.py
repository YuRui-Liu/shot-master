"""风格圣经三段式（全局库 + 注入逻辑）单测。

覆盖研究 §4.1/§4.3：
- 全局库 visual_styles.json 加载出 真人(real)/2D/3D 三类。
- get_style 命中 / 缺失安全（返回 None）。
- inject_style_prompt：
    stage="ref"    → append ref_fingerprint（锁一致性）。
    stage="render" → **不** append fingerprint（避免中性平光污染戏剧打光）。
    两者都 append prompt_suffix + 收尾 negative_suffix（禁字幕常量句）。
"""
from __future__ import annotations

from drama_shot_master.core import style_bible


# ---------------------------------------------------------------- 全局库加载 --
def test_load_styles_returns_three_categories():
    data = style_bible.load_styles()
    styles = data["styles"]
    cats = {s["category"] for s in styles}
    assert cats == {"real", "2D", "3D"}


def test_load_styles_has_default_style_id_pointing_to_existing_style():
    data = style_bible.load_styles()
    default_id = data["default_style_id"]
    ids = {s["style_id"] for s in data["styles"]}
    assert default_id in ids


def test_each_category_has_at_least_two_seeds():
    data = style_bible.load_styles()
    from collections import Counter
    counts = Counter(s["category"] for s in data["styles"])
    for cat in ("real", "2D", "3D"):
        assert counts[cat] >= 2, f"{cat} 应有 ≥2 条 seed 风格"


def test_every_style_has_required_fields():
    data = style_bible.load_styles()
    for s in data["styles"]:
        assert s["style_id"]
        assert s["category"] in ("real", "2D", "3D")
        assert s["name_cn"]
        assert s["source"] == "template"
        assert s["prompt_suffix"]
        assert s["ref_fingerprint"]
        assert s["negative_suffix"]


# ----------------------------------------------------------------- get_style --
def test_get_style_hit():
    s = style_bible.get_style("real/cinematic-warm-v1")
    assert s is not None
    assert s["style_id"] == "real/cinematic-warm-v1"
    assert s["category"] == "real"


def test_get_style_missing_returns_none():
    assert style_bible.get_style("real/does-not-exist") is None


# -------------------------------------------------------- inject_style_prompt --
def _warm_style() -> dict:
    return style_bible.get_style("real/cinematic-warm-v1")


def test_inject_ref_stage_appends_fingerprint():
    style = _warm_style()
    out = style_bible.inject_style_prompt("一个女人站在窗前", style, stage="ref")
    assert style["ref_fingerprint"] in out
    assert style["prompt_suffix"] in out
    assert style["negative_suffix"] in out


def test_inject_render_stage_omits_fingerprint_but_keeps_suffix():
    style = _warm_style()
    out = style_bible.inject_style_prompt("一个女人站在窗前", style, stage="render")
    assert style["ref_fingerprint"] not in out          # 戏剧打光不被中性平光污染
    assert style["prompt_suffix"] in out
    assert style["negative_suffix"] in out


def test_inject_keeps_base_prompt():
    style = _warm_style()
    base = "一个女人站在窗前，黄昏暖光"
    out = style_bible.inject_style_prompt(base, style, stage="render")
    assert base in out


def test_negative_suffix_always_present_in_both_stages():
    style = _warm_style()
    neg = style["negative_suffix"]
    assert neg in style_bible.inject_style_prompt("x", style, stage="ref")
    assert neg in style_bible.inject_style_prompt("x", style, stage="render")


def test_negative_suffix_is_at_the_end():
    style = _warm_style()
    out = style_bible.inject_style_prompt("base", style, stage="render")
    assert out.rstrip().endswith(style["negative_suffix"].rstrip())


def test_inject_default_stage_is_render():
    style = _warm_style()
    out_default = style_bible.inject_style_prompt("base", style)
    out_render = style_bible.inject_style_prompt("base", style, stage="render")
    assert out_default == out_render
