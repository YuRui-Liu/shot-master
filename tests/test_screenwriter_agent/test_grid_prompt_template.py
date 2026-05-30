"""9/4/单帧宫格提示词模板：结构约束 + 尺寸映射 + 上下文注入。"""
from screenwriter_agent.core.template_loader import load_template


def test_grid_template_has_layout_structure():
    text, _ = load_template("grid_prompt")
    for marker in ["# Task", "# Numbering", "# Style", "# Character Lock",
                   "# Sub-frame Descriptions", "# Layout Requirements",
                   "# Final Note", "ONE single", "3×3", "F1", "F9"]:
        assert marker in text, f"模板缺少结构标记: {marker}"


def test_grid_template_has_size_mapping():
    text, _ = load_template("grid_prompt")
    assert "2304×1296" in text          # 16:9 横屏
    assert "1296×2304" in text          # 9:16 竖屏


def test_grid_template_covers_4_and_single():
    text, _ = load_template("grid_prompt")
    assert "2×2" in text                 # 四宫格
    assert "single" in text.lower()      # 单帧


def test_build_grid_user_prompt_includes_context():
    from screenwriter_agent.routes.prompts import build_grid_user_prompt
    sb = {"globalStyle": "ink-wash", "aspectRatio": "9:16",
          "characters": [{"name": "周翠英", "appearance": "red hanfu"}]}
    grp = [{"shotId": "S01", "description": "雨夜", "duration": 4}]
    opts = {"grid_mode": "9", "quality_boost": True,
            "negative_preset": "", "style_extra": ""}
    p = build_grid_user_prompt("TPLBODY", sb, grp, 1, opts)
    assert "TPLBODY" in p
    assert "9:16" in p                   # aspect_ratio 注入（尺寸映射用）
    assert "周翠英" in p and "red hanfu" in p   # characters 注入（Character Lock）
    assert "S01" in p                    # 本组镜头
    assert "ink-wash" in p               # globalStyle
