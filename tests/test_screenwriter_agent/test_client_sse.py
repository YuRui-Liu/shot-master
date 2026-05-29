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
