"""gen_context 注入装配纯函数单测（②a，无 Qt / 无网络 / 用假 dict）。

覆盖（照 spec「注入契约」）：
- build_genre_context：空 dict→空串；非空含 identity/rhythm/爽点%/守则/donts；
  hard_constraints 非空时 ⚠️ 置顶。
- build_style_context：空→空串；复用 inject_style_prompt；
  stage='ref' 含 ref_fingerprint，stage='render' 不含；两阶段都含 prompt_suffix+negative_suffix。
- build_video_director_prompts：导演台结构；length_frames=round(duration*fps)；
  total_frames=Σ；global_prompt 含 style prompt_suffix。
- guard_prompt：禁词替换表 + 超长截断。
"""
from __future__ import annotations

from drama_shot_master.core.gen_context import (
    build_genre_context,
    build_style_context,
    build_video_director_prompts,
    guard_prompt,
)


# --- 假数据 ---------------------------------------------------------------

def _genre(hard=None):
    return {
        "genre_id": "fake-drama",
        "display_name": "假短剧",
        "hard_constraints": hard if hard is not None else [],
        "identity": {
            "one_liner": "钩子密集的竖屏连续剧",
            "audience": "女频 25-40",
            "conflict_source": ["钱", "面子"],
        },
        "rhythm": {
            "open_3s": "黄金三秒抛钩子",
            "open_30s": "立人设交付第一钩",
            "beat_density": "每分钟 4 个爽点",
        },
        "satisfaction_weights": {"打脸": 40, "逆袭": 30, "甜宠": 30},
        "writing_rules": ["爽点必先压抑", "结尾留卡点"],
        "donts": ["不要平铺直叙", "不要无铺垫反转"],
    }


def _style():
    return {
        "style_id": "real/fake-v1",
        "prompt_suffix": "cinematic, warm grade",
        "ref_fingerprint": "neutral flat lighting",
        "negative_suffix": "no subtitles, no watermark",
    }


# --- build_genre_context --------------------------------------------------

def test_build_genre_context_empty_returns_empty():
    assert build_genre_context({}) == ""


def test_build_genre_context_includes_core_sections():
    out = build_genre_context(_genre())
    # identity
    assert "钩子密集的竖屏连续剧" in out
    assert "女频 25-40" in out
    assert "面子" in out
    # rhythm
    assert "黄金三秒抛钩子" in out
    assert "每分钟 4 个爽点" in out
    # satisfaction_weights 爽点 %
    assert "打脸" in out and "40" in out
    # writing_rules
    assert "爽点必先压抑" in out
    # donts
    assert "不要平铺直叙" in out


def test_build_genre_context_hard_constraints_pinned_top_with_warning():
    g = _genre(hard=["禁止未成年", "禁止血腥"])
    out = build_genre_context(g)
    assert "⚠️" in out
    assert "禁止未成年" in out
    # 硬约束置顶：出现在 identity one_liner 之前
    assert out.index("禁止未成年") < out.index("钩子密集的竖屏连续剧")


def test_build_genre_context_no_hard_constraints_no_warning():
    out = build_genre_context(_genre(hard=[]))
    assert "⚠️" not in out


# --- build_style_context --------------------------------------------------

def test_build_style_context_empty_returns_empty():
    assert build_style_context({}, stage="render") == ""


def test_build_style_context_render_excludes_fingerprint():
    out = build_style_context(_style(), stage="render")
    assert "cinematic, warm grade" in out
    assert "no subtitles, no watermark" in out
    assert "neutral flat lighting" not in out


def test_build_style_context_ref_includes_fingerprint():
    out = build_style_context(_style(), stage="ref")
    assert "neutral flat lighting" in out
    assert "cinematic, warm grade" in out
    assert "no subtitles, no watermark" in out


# --- build_video_director_prompts ----------------------------------------

def _storyboard():
    return {
        "shots": [
            {"id": "S001", "description": "女主推门而入，怒视全场", "duration": 3.0},
            {"prompt": "特写茶杯落地碎裂", "duration": 2.0},
        ]
    }


def test_build_video_director_prompts_structure_and_frames():
    out = build_video_director_prompts(
        _storyboard(), _style(), _genre(), fps=24
    )
    assert out["fps"] == 24
    assert len(out["shots"]) == 2
    s0, s1 = out["shots"]
    # frames = round(duration * fps)
    assert s0["length_frames"] == 72
    assert s1["length_frames"] == 48
    assert s0["duration"] == 3.0
    # shot_id：给了 id 用 id，没给则自动 S00n
    assert s0["shot_id"] == "S001"
    assert s1["shot_id"] == "S002"
    # 镜头描述进 prompt
    assert "女主推门而入" in s0["prompt"]
    assert "特写茶杯落地碎裂" in s1["prompt"]
    # 风格注入每个 shot
    assert "cinematic, warm grade" in s0["prompt"]
    # total_frames = Σ
    assert out["total_frames"] == 72 + 48


def test_build_video_director_prompts_global_contains_style():
    out = build_video_director_prompts(_storyboard(), _style(), _genre(), fps=24)
    assert "cinematic, warm grade" in out["global_prompt"]


def test_build_video_director_prompts_default_duration():
    sb = {"shots": [{"description": "无时长镜头"}]}
    out = build_video_director_prompts(sb, _style(), _genre(), fps=24)
    # Shot.duration 默认 3.0
    assert out["shots"][0]["length_frames"] == 72
    assert out["total_frames"] == 72


def test_build_video_director_prompts_empty_shots():
    out = build_video_director_prompts({"shots": []}, _style(), _genre(), fps=24)
    assert out["shots"] == []
    assert out["total_frames"] == 0


# --- guard_prompt ---------------------------------------------------------

def test_guard_prompt_replaces_banned_words():
    out = guard_prompt("a sinister figure with blush, extreme close-up shot")
    assert "sinister" not in out
    assert "moody" in out
    assert "blush" not in out
    assert "rose tint" in out
    assert "extreme close-up" not in out
    assert "medium shot" in out


def test_guard_prompt_truncates_over_max():
    long = "x" * 2000
    out = guard_prompt(long, max_chars=1400)
    assert len(out) <= 1400


def test_guard_prompt_short_unchanged_length():
    text = "a calm scene"
    out = guard_prompt(text, max_chars=1400)
    assert out == "a calm scene"
