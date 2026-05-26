from drama_shot_master.core.dub_task_store import DubTask, DubTaskStore


def test_add_and_get():
    s = DubTaskStore()
    t = s.add("配音A", mode="clone", payload={"text": "hi"})
    assert isinstance(t, DubTask) and t.name == "配音A" and t.mode == "clone"
    assert s.get(t.id) is t
    assert t.payload["text"] == "hi"


def test_update_and_remove():
    s = DubTaskStore()
    t = s.add("A", mode="design", payload={})
    s.update(t.id, name="B", last_result="/x/o.flac")
    assert s.get(t.id).name == "B"
    assert s.get(t.id).last_result == "/x/o.flac"
    s.remove(t.id)
    assert s.get(t.id) is None


def test_duplicate():
    s = DubTaskStore()
    t = s.add("A", mode="clone", payload={"text": "hi", "mode": 2})
    d = s.duplicate(t.id)
    assert d.id != t.id and d.payload == t.payload and d.mode == t.mode
    assert "副本" in d.name or d.name != t.name


def test_to_from_list_roundtrip():
    s = DubTaskStore()
    s.add("A", mode="design", payload={"text": "t", "style": "s", "language": "Auto"})
    s.add("B", mode="clone", payload={"text": "x", "mode": 4})
    data = s.to_list()
    s2 = DubTaskStore.from_list(data)
    assert [t.name for t in s2.all()] == ["A", "B"]
    assert s2.all()[1].payload["mode"] == 4
