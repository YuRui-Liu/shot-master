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
