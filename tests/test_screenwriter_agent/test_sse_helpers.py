from screenwriter_agent.core.sse import sse_event


def test_sse_event_basic():
    out = sse_event("delta", {"text": "abc"})
    assert "event: delta" in out
    assert "data: " in out
    assert '"text"' in out
    assert "abc" in out
    assert out.endswith("\n\n")


def test_sse_event_unicode_safe():
    out = sse_event("status", {"phase": "生成中"})
    assert "生成中" in out
