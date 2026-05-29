import pytest

from drama_shot_master.agents.screenwriter_client import parse_sse_lines


def test_parse_sse_events():
    raw = (
        "event: status\n"
        'data: {"phase": "thinking"}\n'
        "\n"
        "event: delta\n"
        'data: {"text": "hi"}\n'
        "\n"
        "event: done\n"
        'data: {"saved": "/x.json"}\n'
        "\n"
    )
    events = list(parse_sse_lines(raw.splitlines(keepends=True)))
    assert [e["event"] for e in events] == ["status", "delta", "done"]
    assert events[1]["data"]["text"] == "hi"


def test_stream_post_accepts_params(monkeypatch):
    """stream_post 接受可选 params=dict，透传到 httpx.stream() 的 params 参数。"""
    from drama_shot_master.agents.screenwriter_client import ScreenwriterClient
    captured = {}

    class _FakeResp:
        status_code = 200
        def raise_for_status(self): pass
        def iter_lines(self): return iter([])
        def __enter__(self): return self
        def __exit__(self, *a): pass

    class _FakeClient:
        def stream(self, method, url, json=None, params=None):
            captured["method"] = method
            captured["url"] = url
            captured["params"] = params
            return _FakeResp()
        def __enter__(self): return self
        def __exit__(self, *a): pass

    import drama_shot_master.agents.screenwriter_client as m
    monkeypatch.setattr(m, "httpx",
                        type("X", (), {"Client": lambda *a, **kw: _FakeClient()}))
    c = ScreenwriterClient("http://localhost:18430")
    list(c.stream_post("/foo", {"bar": 1}, params={"purge_downstream": "true"}))
    assert captured["params"] == {"purge_downstream": "true"}


def test_stream_post_surfaces_agent_error_body_on_4xx(monkeypatch):
    """4xx 时应读取 agent 结构化错误体并抛含 code/message/hint 的异常，
    而非吞掉 body 抛通用 httpx '400 Bad Request'。"""
    from drama_shot_master.agents.screenwriter_client import ScreenwriterClient

    class _FakeResp:
        status_code = 400

        def read(self):
            return b""

        def json(self):
            return {"error": {"code": "UPSTREAM_PRODUCT_MISSING",
                              "message": "剧本.json missing",
                              "hint": "请先在剧本阶段生成大纲。"}}

        @property
        def text(self):
            return "ignored"

        def raise_for_status(self):
            raise AssertionError("不应调用 raise_for_status — 应先读取错误体")

        def iter_lines(self):
            return iter([])

        def __enter__(self): return self
        def __exit__(self, *a): pass

    class _FakeClient:
        def stream(self, method, url, json=None, params=None):
            return _FakeResp()
        def __enter__(self): return self
        def __exit__(self, *a): pass

    import drama_shot_master.agents.screenwriter_client as m
    monkeypatch.setattr(m, "httpx",
                        type("X", (), {"Client": lambda *a, **kw: _FakeClient()}))
    c = ScreenwriterClient("http://localhost:18430")
    with pytest.raises(Exception) as ei:
        list(c.stream_post("/script/episode", {"bar": 1}))
    msg = str(ei.value)
    assert "UPSTREAM_PRODUCT_MISSING" in msg
    assert "剧本.json missing" in msg
    assert "请先在剧本阶段生成大纲" in msg
