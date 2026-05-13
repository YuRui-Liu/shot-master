import pytest
from pathlib import Path
from app.core.template_engine import (
    Template, TemplateVariable, load_template, list_templates,
    render_template, recommend_template,
)


SAMPLE_MD = """---
name: 四帧测试
suggest_when: image_count == 4
variables:
  - name: total_seconds
    type: int
    default: 16
    label: 总时长
    required: true
  - name: fps
    type: int
    default: 24
    label: FPS
    required: true
  - name: style_note
    type: textarea
    label: 风格备注
    optional: true
---
你是 LTX 提示词工程师。total={{total_seconds}}s, fps={{fps}}, style={{style_note}}.
"""


def test_load_template(tmp_path):
    p = tmp_path / "four_frame.md"
    p.write_text(SAMPLE_MD, encoding="utf-8")
    tpl = load_template(p)
    assert tpl.id == "four_frame"
    assert tpl.name == "四帧测试"
    assert tpl.suggest_when == "image_count == 4"
    assert len(tpl.variables) == 3
    assert tpl.variables[0].name == "total_seconds"
    assert tpl.variables[0].type == "int"
    assert tpl.variables[0].default == 16
    assert tpl.variables[0].required is True
    assert tpl.variables[2].optional is True
    assert "你是 LTX 提示词工程师" in tpl.body


def test_render_template_substitutes_placeholders(tmp_path):
    p = tmp_path / "t.md"
    p.write_text(SAMPLE_MD, encoding="utf-8")
    tpl = load_template(p)
    out = render_template(tpl, {"total_seconds": 20, "fps": 30, "style_note": "墨韵"})
    assert "total=20s" in out
    assert "fps=30" in out
    assert "style=墨韵" in out


def test_render_uses_defaults_for_missing(tmp_path):
    p = tmp_path / "t.md"
    p.write_text(SAMPLE_MD, encoding="utf-8")
    tpl = load_template(p)
    out = render_template(tpl, {"style_note": "暗调"})
    assert "total=16s" in out
    assert "fps=24" in out


def test_render_raises_when_required_missing(tmp_path):
    p = tmp_path / "t.md"
    md = SAMPLE_MD.replace("default: 16\n    label: 总时长", "label: 总时长")
    p.write_text(md, encoding="utf-8")
    tpl = load_template(p)
    with pytest.raises(ValueError, match="total_seconds"):
        render_template(tpl, {"fps": 24})


def test_list_templates(tmp_path):
    (tmp_path / "a.md").write_text(SAMPLE_MD.replace("四帧测试", "A"), encoding="utf-8")
    (tmp_path / "b.md").write_text(SAMPLE_MD.replace("四帧测试", "B"), encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("nope")
    tpls = list_templates(tmp_path)
    assert {t.id for t in tpls} == {"a", "b"}


def test_recommend_template_by_image_count(tmp_path):
    t1 = SAMPLE_MD.replace("四帧测试", "三帧").replace(
        "image_count == 4", "image_count == 3"
    )
    t4 = SAMPLE_MD.replace("四帧测试", "四帧")
    tn = SAMPLE_MD.replace("四帧测试", "多帧").replace(
        "image_count == 4", "image_count >= 5"
    )
    (tmp_path / "three.md").write_text(t1, encoding="utf-8")
    (tmp_path / "four.md").write_text(t4, encoding="utf-8")
    (tmp_path / "multi.md").write_text(tn, encoding="utf-8")
    tpls = list_templates(tmp_path)
    assert recommend_template(tpls, image_count=3).id == "three"
    assert recommend_template(tpls, image_count=4).id == "four"
    assert recommend_template(tpls, image_count=7).id == "multi"


def test_recommend_returns_none_when_no_match(tmp_path):
    (tmp_path / "x.md").write_text(SAMPLE_MD.replace("四帧测试", "Only4"), encoding="utf-8")
    tpls = list_templates(tmp_path)
    assert recommend_template(tpls, image_count=99) is None
