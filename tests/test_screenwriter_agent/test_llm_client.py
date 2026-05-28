import pytest
from screenwriter_agent.core.llm_client import LLMClient, StreamChunk


def _fake_stream(text="hello"):
    """模拟 OpenAI SDK 的 chunk iterator：每个 chunk 含 delta.content。"""
    class _D:
        def __init__(self, content): self.content = content
    class _C:
        def __init__(self, content): self.delta = _D(content)
    class _Ch:
        def __init__(self, content): self.choices = [_C(content)]
    for ch in text:
        yield _Ch(ch)
    yield _Ch("")    # 收尾空 chunk


def test_iter_text_chunks_yields_deltas(monkeypatch):
    client = LLMClient(api_key="dummy", base_url="https://example", model="m")
    fake_stream = _fake_stream("abc")
    monkeypatch.setattr(client, "_raw_stream",
                        lambda **kw: fake_stream)
    chunks = list(client.stream_chat([{"role": "user", "content": "x"}]))
    deltas = [c.text for c in chunks if c.kind == "delta"]
    assert "".join(deltas) == "abc"
