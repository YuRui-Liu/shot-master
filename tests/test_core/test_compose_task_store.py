from drama_shot_master.core.compose_task_store import ComposeTask, ComposeTaskStore


def test_add_get_update_remove():
    s = ComposeTaskStore()
    t = s.add("第一集 · 成片", {"clips": []})
    assert s.get(t.id) is t
    s.update(t.id, output_mp4="/out/compose_x.mp4", name="改名")
    assert s.get(t.id).output_mp4.endswith("compose_x.mp4")
    assert s.get(t.id).name == "改名"
    s.remove(t.id)
    assert s.get(t.id) is None


def test_to_from_list_roundtrip():
    s = ComposeTaskStore()
    s.add("A", {"clips": [{"clip_id": "1", "path": "/a.mp4"}]})
    data = s.to_list()
    s2 = ComposeTaskStore.from_list(data)
    assert s2.all()[0].name == "A"
    assert s2.all()[0].composition["clips"][0]["path"] == "/a.mp4"
