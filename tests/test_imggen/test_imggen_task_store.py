from drama_shot_master.core.imggen_task_store import ImgGenTask, ImgGenTaskStore


def test_add_get_update_remove():
    s = ImgGenTaskStore()
    t = s.add("出图A", payload={"prompt": "猫", "n": 1})
    assert isinstance(t, ImgGenTask) and s.get(t.id) is t
    s.update(t.id, name="B", last_result="/x/o.png")
    assert s.get(t.id).name == "B" and s.get(t.id).last_result == "/x/o.png"
    s.remove(t.id)
    assert s.get(t.id) is None


def test_duplicate_and_roundtrip():
    s = ImgGenTaskStore()
    t = s.add("A", payload={"prompt": "p", "refs": [{"path": "/a.png", "label": "图1"}]})
    d = s.duplicate(t.id)
    assert d.id != t.id and d.payload == t.payload
    s2 = ImgGenTaskStore.from_list(s.to_list())
    assert [x.name for x in s2.all()] == ["A", "A 副本"]
    assert s2.all()[0].payload["refs"][0]["label"] == "图1"
