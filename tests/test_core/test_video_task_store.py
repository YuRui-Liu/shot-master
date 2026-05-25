"""Tests for VideoTaskStore."""
from __future__ import annotations

from drama_shot_master.core.video_task_store import VideoTask, VideoTaskStore


def test_add_appends_with_id_and_timestamp():
    s = VideoTaskStore()
    t = s.add("任务 A", {"segments": []})
    assert t.id
    assert t.name == "任务 A"
    assert t.timeline == {"segments": []}
    assert t.updated_at > 0
    assert s.all() == [t]


def test_get_by_id():
    s = VideoTaskStore()
    t = s.add("A", {})
    assert s.get(t.id) is t
    assert s.get("nope") is None


def test_update_fields_refreshes_timestamp():
    s = VideoTaskStore()
    t = s.add("A", {})
    old_ts = t.updated_at
    s.update(t.id, name="B", timeline={"x": 1}, last_result="/o/v.mp4")
    g = s.get(t.id)
    assert g.name == "B"
    assert g.timeline == {"x": 1}
    assert g.last_result == "/o/v.mp4"
    assert g.updated_at >= old_ts


def test_remove():
    s = VideoTaskStore()
    t = s.add("A", {})
    s.remove(t.id)
    assert s.get(t.id) is None
    assert s.all() == []


def test_duplicate_is_deep_and_named():
    s = VideoTaskStore()
    t = s.add("A", {"segments": [{"seg_id": "x"}]})
    dup = s.duplicate(t.id)
    assert dup.id != t.id
    assert "副本" in dup.name
    dup.timeline["segments"].append({"seg_id": "y"})
    assert len(s.get(t.id).timeline["segments"]) == 1


def test_roundtrip_to_from_list():
    s = VideoTaskStore()
    s.add("A", {"a": 1})
    s.add("B", {"b": 2})
    data = s.to_list()
    s2 = VideoTaskStore.from_list(data)
    assert [t.name for t in s2.all()] == ["A", "B"]
    assert s2.all()[0].timeline == {"a": 1}


def test_from_list_tolerates_missing_optional_fields():
    s = VideoTaskStore.from_list([{"id": "1", "name": "A", "timeline": {}}])
    t = s.all()[0]
    assert t.last_result == ""
    assert t.updated_at == 0.0
