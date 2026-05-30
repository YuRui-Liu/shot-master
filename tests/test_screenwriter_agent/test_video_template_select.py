"""视频提示词：LTX2.3 模板选择 + 语言注入。"""
from screenwriter_agent.models.requests import VideoPromptOptions
from screenwriter_agent.core.template_loader import load_template


def test_video_options_defaults_ltx_en():
    o = VideoPromptOptions()
    assert o.template_id == "ltx"          # 新模板默认
    assert o.language == "en"              # 默认全英文


def test_video_template_id_maps():
    from screenwriter_agent.routes.video_prompt import video_template_id
    assert video_template_id("ltx") == "video_prompt_ltx"
    assert video_template_id("simple") == "video_prompt"
    assert video_template_id("default") == "video_prompt"


def test_build_video_user_prompt_injects_language():
    from screenwriter_agent.routes.video_prompt import build_video_user_prompt
    tpl = "BODY lang={language} fps={fps} ar={aspect_ratio} sb={storyboard_json}"
    opts = VideoPromptOptions(language="zh", fps=24, aspect_ratio="9:16")
    p = build_video_user_prompt(tpl, {"shots": []}, opts)
    assert "lang=zh" in p
    assert "fps=24" in p


def test_ltx_template_has_anti_ppt_and_both_label_sets():
    text, _ = load_template("video_prompt_ltx")
    for m in ["反 PPT", "画面", "运镜", "音效",
              "Scene", "Camera", "Audio", "{language}"]:
        assert m in text, f"模板缺少: {m}"
