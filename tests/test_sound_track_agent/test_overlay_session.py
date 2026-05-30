"""OverlaySession：叠加片段 + 自动分轨 + overlay.json 持久化。"""
from sound_track_agent.overlay_session import (
    OverlaySegment, OverlaySession, load_overlay, save_overlay)


def test_segment_roundtrip():
    s = OverlaySegment(id="x1", kind="bgm", lane=0, t_start=1.0, t_end=5.0,
                       prompt="史诗", audio_path="/a.mp3", volume=0.8, enabled=False)
    s2 = OverlaySegment.from_dict(s.to_dict())
    assert s2 == s


def test_segment_defaults():
    s = OverlaySegment(id="x", kind="sfx", lane=0, t_start=0.0, t_end=2.0, prompt="门")
    assert s.audio_path == "" and s.volume == 1.0 and s.enabled is True


def test_add_first_segment_lane0():
    sess = OverlaySession()
    seg = sess.add("bgm", 0.0, 5.0, "a", seg_id="s1")
    assert seg.lane == 0 and seg.kind == "bgm"
    assert len(sess.segments) == 1


def test_add_non_overlapping_same_lane():
    sess = OverlaySession()
    sess.add("bgm", 0.0, 5.0, "a", seg_id="s1")
    seg2 = sess.add("bgm", 5.0, 9.0, "b", seg_id="s2")   # 边界相接，不重叠
    assert seg2.lane == 0


def test_add_overlapping_new_lane():
    sess = OverlaySession()
    sess.add("bgm", 0.0, 5.0, "a", seg_id="s1")
    seg2 = sess.add("bgm", 3.0, 8.0, "b", seg_id="s2")   # 重叠
    assert seg2.lane == 1


def test_add_third_fills_lowest_free_lane():
    sess = OverlaySession()
    sess.add("bgm", 0.0, 5.0, "a", seg_id="s1")          # lane0
    sess.add("bgm", 3.0, 8.0, "b", seg_id="s2")          # lane1
    seg3 = sess.add("bgm", 6.0, 9.0, "c", seg_id="s3")   # 与lane0(0-5)不重叠 → lane0
    assert seg3.lane == 0


def test_bgm_sfx_independent_lanes():
    sess = OverlaySession()
    b = sess.add("bgm", 0.0, 5.0, "a", seg_id="b1")
    s = sess.add("sfx", 0.0, 5.0, "x", seg_id="s1")
    assert b.lane == 0 and s.lane == 0                   # 各自独立从 0


def test_lanes_for():
    sess = OverlaySession()
    assert sess.lanes_for("bgm") == 0
    sess.add("bgm", 0.0, 5.0, "a", seg_id="s1")
    sess.add("bgm", 3.0, 8.0, "b", seg_id="s2")
    assert sess.lanes_for("bgm") == 2
    assert sess.lanes_for("sfx") == 0


def test_segments_in_lane():
    sess = OverlaySession()
    sess.add("bgm", 0.0, 5.0, "a", seg_id="s1")
    sess.add("bgm", 6.0, 9.0, "c", seg_id="s3")          # 同 lane0
    sess.add("bgm", 3.0, 8.0, "b", seg_id="s2")          # lane1
    lane0 = sess.segments_in_lane("bgm", 0)
    assert {s.id for s in lane0} == {"s1", "s3"}


def test_remove_and_get():
    sess = OverlaySession()
    sess.add("bgm", 0.0, 5.0, "a", seg_id="s1")
    assert sess.get("s1") is not None
    assert sess.remove("s1") is True
    assert sess.get("s1") is None
    assert sess.remove("nope") is False


def test_session_roundtrip():
    sess = OverlaySession()
    sess.add("bgm", 0.0, 5.0, "a", seg_id="s1")
    sess.add("sfx", 1.0, 2.0, "x", seg_id="s2")
    sess2 = OverlaySession.from_dict(sess.to_dict())
    assert len(sess2.segments) == 2
    assert sess2.get("s1").prompt == "a"


def test_save_load_roundtrip(tmp_path):
    sess = OverlaySession()
    sess.add("bgm", 0.0, 5.0, "a", seg_id="s1")
    save_overlay(tmp_path, sess)
    sess2 = load_overlay(tmp_path)
    assert sess2.get("s1").t_end == 5.0


def test_load_missing_returns_empty(tmp_path):
    assert load_overlay(tmp_path).segments == []


def test_load_corrupt_returns_empty(tmp_path):
    (tmp_path / "overlay.json").write_text("{bad", encoding="utf-8")
    assert load_overlay(tmp_path).segments == []
