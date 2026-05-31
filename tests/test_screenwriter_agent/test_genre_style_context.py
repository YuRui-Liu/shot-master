"""②c 题材+风格驱动（架构 A 客户端组装）：

screenwriter_agent 侧验证——
1) requests 模型新增 genre_context / style_context 字段（默认空，向后兼容）；
2) 各 route 的 prompt 装配函数：非空时把题材规则/风格注入装配出的 prompt；
   空字段 → prompt 不含这些文本、且行为与现状一致。

不真连 LLM：直接调用纯装配函数断言字符串。
"""
from __future__ import annotations

import json

from screenwriter_agent.models.requests import (
    IdeateContext, ScriptOptions, StoryboardOptions, PromptsOptions,
    VideoPromptOptions,
)


# ---------------- requests 字段（默认空 + 可填，向后兼容） ----------------

def test_request_models_default_context_empty():
    assert IdeateContext().genre_context == ""
    assert IdeateContext().style_context == ""
    assert ScriptOptions().genre_context == ""
    assert ScriptOptions().style_context == ""
    assert StoryboardOptions().genre_context == ""
    assert StoryboardOptions().style_context == ""
    assert PromptsOptions().genre_context == ""
    assert PromptsOptions().style_context == ""
    assert PromptsOptions().style_context_ref == ""
    assert VideoPromptOptions().genre_context == ""
    assert VideoPromptOptions().style_context == ""


def test_request_models_accept_context():
    ic = IdeateContext(genre_context="题材G", style_context="风格S")
    assert ic.genre_context == "题材G" and ic.style_context == "风格S"
    so = StoryboardOptions(genre_context="题材G", style_context="风格S")
    assert so.genre_context == "题材G" and so.style_context == "风格S"
    po = PromptsOptions(style_context="风格R", style_context_ref="风格REF")
    assert po.style_context == "风格R" and po.style_context_ref == "风格REF"


# ---------------- ideate.py：system_msg 末尾追加 genre_context ----------------

def test_ideate_system_content_appends_genre_when_present():
    from screenwriter_agent.routes.ideate import build_ideate_system_content
    ctx = IdeateContext(genre_context="GENRE_RULES_XYZ").model_dump()
    content = build_ideate_system_content("TPL", ctx)
    assert "TPL" in content
    assert "## 题材规则" in content
    assert "GENRE_RULES_XYZ" in content


def test_ideate_system_content_empty_genre_omits_section():
    from screenwriter_agent.routes.ideate import build_ideate_system_content
    ctx = IdeateContext().model_dump()
    content = build_ideate_system_content("TPL", ctx)
    assert "## 题材规则" not in content
    # 向后兼容：基础结构保持
    assert "TPL" in content and "## 当前 context" in content


# ---------------- script_outline.py：prompt 追加 '## 题材规则' ----------------

def test_outline_prompt_appends_genre_when_present():
    from screenwriter_agent.routes.script_outline import build_outline_prompt
    opts = ScriptOptions(genre_context="GENRE_OUTLINE_42").model_dump()
    p = build_outline_prompt("TPL", {"id": "c1"}, 3, opts)
    assert "## 题材规则" in p
    assert "GENRE_OUTLINE_42" in p
    assert "**只输出一个 JSON 代码块**" in p


def test_outline_prompt_empty_genre_omits():
    from screenwriter_agent.routes.script_outline import build_outline_prompt
    opts = ScriptOptions().model_dump()
    p = build_outline_prompt("TPL", {"id": "c1"}, 3, opts)
    assert "## 题材规则" not in p
    assert "episode_count=3" in p


# ---------------- storyboard.py：题材规则 + globalStyle 初值用 style_context ----

def test_storyboard_prompt_appends_genre_and_style_when_present():
    from screenwriter_agent.routes.storyboard import build_storyboard_prompt
    opts = StoryboardOptions(genre_context="GENRE_SB_7",
                             style_context="STYLE_SB_BIBLE").model_dump()
    p = build_storyboard_prompt("TPL", "剧本正文", opts)
    assert "## 题材规则" in p and "GENRE_SB_7" in p
    assert "STYLE_SB_BIBLE" in p
    assert "globalStyle" in p  # 风格作为 globalStyle 初值注入


def test_storyboard_prompt_empty_context_omits():
    from screenwriter_agent.routes.storyboard import build_storyboard_prompt
    opts = StoryboardOptions().model_dump()
    p = build_storyboard_prompt("TPL", "剧本正文", opts)
    assert "## 题材规则" not in p
    assert "GENRE" not in p
    assert "剧本正文" in p
    assert "**只输出一个 JSON 代码块**" in p


# ---------------- prompts.py：grid globalStyle=style_context(render)；ref 用 ref 阶段 ----

def test_grid_prompt_uses_style_context_render_when_present():
    from screenwriter_agent.routes.prompts import build_grid_user_prompt
    sb = {"globalStyle": "OLD_SB_STYLE", "characters": [], "shots": []}
    opts = PromptsOptions(style_context="RENDER_STYLE_99").model_dump()
    p = build_grid_user_prompt("TPL", sb, [], 1, opts)
    assert "RENDER_STYLE_99" in p
    assert "OLD_SB_STYLE" not in p  # style_context 覆盖 storyboard.globalStyle


def test_grid_prompt_falls_back_to_sb_globalstyle_when_empty():
    from screenwriter_agent.routes.prompts import build_grid_user_prompt
    sb = {"globalStyle": "OLD_SB_STYLE", "characters": [], "shots": []}
    opts = PromptsOptions().model_dump()
    p = build_grid_user_prompt("TPL", sb, [], 1, opts)
    assert "OLD_SB_STYLE" in p  # 向后兼容：回退 storyboard.globalStyle


def test_char_ref_prompt_uses_style_context_ref_when_present():
    from screenwriter_agent.routes.prompts import build_char_ref_prompt
    sb = {"globalStyle": "OLD_SB_STYLE"}
    opts = PromptsOptions(style_context_ref="REF_STYLE_FP").model_dump()
    p = build_char_ref_prompt("TPL", {"name": "小明"}, sb, opts)
    assert "REF_STYLE_FP" in p
    assert "OLD_SB_STYLE" not in p


def test_char_ref_prompt_falls_back_when_empty():
    from screenwriter_agent.routes.prompts import build_char_ref_prompt
    sb = {"globalStyle": "OLD_SB_STYLE"}
    opts = PromptsOptions().model_dump()
    p = build_char_ref_prompt("TPL", {"name": "小明"}, sb, opts)
    assert "OLD_SB_STYLE" in p


# ---------------- video_prompt.py：导演台 global_prompt 用 style_context ----------

def test_video_prompt_appends_style_and_genre_when_present():
    from screenwriter_agent.routes.video_prompt import build_video_user_prompt
    # 模板含各占位符（保持 global+per-shot+时间结构由模板本体承载）
    tpl = ("SB={storyboard_json} FPS={fps} AR={aspect_ratio} L={language}")
    opts = VideoPromptOptions(style_context="DIRECTOR_STYLE_GLOBAL",
                              genre_context="VIDEO_GENRE_TONE")
    sb = {"shots": [{"shot_id": "S001", "duration": 4}]}
    p = build_video_user_prompt(tpl, sb, opts)
    assert "DIRECTOR_STYLE_GLOBAL" in p
    assert "global_prompt" in p  # 提示模型据此产出导演台 global_prompt
    assert "VIDEO_GENRE_TONE" in p
    # 时间/分镜结构仍在（storyboard JSON 含 shot_id/duration）
    assert "S001" in p


def test_video_prompt_empty_context_omits():
    from screenwriter_agent.routes.video_prompt import build_video_user_prompt
    tpl = ("SB={storyboard_json} FPS={fps} AR={aspect_ratio} L={language}")
    opts = VideoPromptOptions()
    sb = {"shots": [{"shot_id": "S001", "duration": 4}]}
    p = build_video_user_prompt(tpl, sb, opts)
    assert "导演台全局风格" not in p
    assert "题材基调" not in p
    assert "S001" in p  # 向后兼容：基础结构不变
