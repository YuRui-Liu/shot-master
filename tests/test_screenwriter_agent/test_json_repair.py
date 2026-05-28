import pytest
from screenwriter_agent.core.json_repair import RepairResult, repair_json_text


def test_clean_json_passes_through():
    r = repair_json_text('{"a": 1, "b": "x"}')
    assert r.ok is True
    assert r.obj == {"a": 1, "b": "x"}
    assert r.steps == ["strict"]


def test_strips_markdown_codefence():
    raw = '```json\n{"a": 1}\n```'
    r = repair_json_text(raw)
    assert r.ok is True and r.obj == {"a": 1}
    assert "strip_codefence" in r.steps


def test_strips_text_before_brace():
    raw = '这是一段说明文字\n\n{"a": 1}'
    r = repair_json_text(raw)
    assert r.ok is True and r.obj == {"a": 1}


def test_trailing_comma_handled_by_json5_or_regex():
    """json5 可处理；不可用时 regex 兜底也能处理 ,] / ,}."""
    raw = '{"a": 1, "b": [1, 2, 3,],}'
    r = repair_json_text(raw)
    assert r.ok is True and r.obj == {"a": 1, "b": [1, 2, 3]}
    assert "json5" in r.steps or "regex" in r.steps


def test_regex_fixes_chinese_quotes():
    raw = '{"a"：1, "b": "x"}'    # 中文冒号
    r = repair_json_text(raw)
    assert r.ok is True and r.obj == {"a": 1, "b": "x"}
    assert "regex" in r.steps


def test_returns_failed_on_garbage():
    r = repair_json_text("this is not json at all")
    assert r.ok is False
    assert r.obj is None
    assert isinstance(r.raw, str)
