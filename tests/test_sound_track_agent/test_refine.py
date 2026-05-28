from pathlib import Path

from sound_track_agent.refine import refine_segments
from sound_track_agent.segment_planner import Shot
from sound_track_agent.session import (
    ScoringSession, SegmentScore, EmotionTag, BGMCandidate,
)


def _session(tmp_path, *, candidates=None):
    seg = SegmentScore(index=0, t_start=0.0, t_end=2.0)
    if candidates is not None:
        seg.candidates = list(candidates)
    return ScoringSession(
        source_mp4=str(tmp_path / "ep.mp4"), source_hash="h",
        global_style="末日", frame_rate=24.0, segments=[seg])


def test_refine_replaces_segments_with_emotion_filled(tmp_path):
    sess = _session(tmp_path)
    fake_shots = [Shot(0, 0.0, 1.0), Shot(1, 1.0, 2.0), Shot(2, 2.0, 3.0)]
    emos = [
        EmotionTag(labels=["calm"], valence=0.0, arousal=0.2, intensity=0.4),
        EmotionTag(labels=["calm"], valence=0.0, arousal=0.2, intensity=0.4),
        EmotionTag(labels=["tense"], valence=-0.5, arousal=0.9, intensity=0.8),
    ]
    call_log = {"detect": 0, "extract": 0, "tag": 0}

    def fake_detect(v):
        call_log["detect"] += 1
        return fake_shots

    def fake_extract(v, times, out_dir):
        call_log["extract"] += 1
        return [Path(out_dir) / f"f{i}.png" for i in range(len(times))]

    def fake_tag(frame_paths):
        i = call_log["tag"]
        call_log["tag"] += 1
        return emos[i]

    ok = refine_segments(
        sess, video_path=tmp_path / "ep.mp4", work_dir=tmp_path / "w",
        provider=None, global_style="末日",
        max_segments=5, merge_threshold=0.25,
        detect=fake_detect, extract_frames=fake_extract, tag_fn=fake_tag)
    assert ok is True
    assert len(sess.segments) == 2
    assert sess.segments[0].shot_ids == [0, 1]
    assert sess.segments[1].shot_ids == [2]
    assert all(s.emotion is not None for s in sess.segments)
    assert all(s.status == "tagged" for s in sess.segments)
    assert call_log["detect"] == 1
    assert call_log["extract"] == 3
    assert call_log["tag"] == 3


def test_refine_safety_gate_when_session_has_candidates(tmp_path):
    """已有候选段 → 返回 False、不替换。"""
    sess = _session(tmp_path,
                    candidates=[BGMCandidate(path="/b.mp3", seed=1, prompt="t")])
    original_segs = list(sess.segments)
    ok = refine_segments(
        sess, video_path=tmp_path / "ep.mp4", work_dir=tmp_path / "w",
        provider=None, global_style="末日",
        detect=lambda v: [Shot(0, 0.0, 1.0)],
        extract_frames=lambda *a, **k: [Path("/x.png")],
        tag_fn=lambda paths: EmotionTag())
    assert ok is False
    assert sess.segments == original_segs


def test_refine_no_shots_returns_false(tmp_path):
    sess = _session(tmp_path)
    ok = refine_segments(
        sess, video_path=tmp_path / "ep.mp4", work_dir=tmp_path / "w",
        provider=None, global_style="x",
        detect=lambda v: [],
        extract_frames=lambda *a, **k: [],
        tag_fn=lambda paths: EmotionTag())
    assert ok is False


def test_refine_degrades_on_detect_exception(tmp_path):
    sess = _session(tmp_path)
    original_segs = list(sess.segments)
    def boom(v): raise RuntimeError("PySceneDetect down")
    ok = refine_segments(
        sess, video_path=tmp_path / "ep.mp4", work_dir=tmp_path / "w",
        provider=None, global_style="x",
        detect=boom,
        extract_frames=lambda *a, **k: [],
        tag_fn=lambda paths: EmotionTag())
    assert ok is False
    assert sess.segments == original_segs


def test_refine_short_shot_uses_single_mid_frame(tmp_path):
    """shot 时长 < 0.1s → 只抽 mid 一帧。"""
    sess = _session(tmp_path)
    captured_times = []
    def fake_extract(v, times, out_dir):
        captured_times.append(list(times))
        return [Path(out_dir) / f"f{i}.png" for i in range(len(times))]
    refine_segments(
        sess, video_path=tmp_path / "ep.mp4", work_dir=tmp_path / "w",
        provider=None, global_style="x",
        detect=lambda v: [Shot(0, 1.000, 1.050)],
        extract_frames=fake_extract,
        tag_fn=lambda paths: EmotionTag())
    assert len(captured_times) == 1
    assert len(captured_times[0]) == 1
    assert abs(captured_times[0][0] - 1.025) < 1e-6


def test_refine_safety_gate_when_session_has_music_prompt(tmp_path):
    """已填 music_prompt 的段（Phase 1/2 老 session 升级）→ 返回 False、不替换。"""
    seg = SegmentScore(index=0, t_start=0.0, t_end=2.0,
                       status="prompted", music_prompt="Instrumental tense")
    sess = ScoringSession(source_mp4=str(tmp_path / "ep.mp4"), source_hash="h",
                          global_style="末日", frame_rate=24.0, segments=[seg])
    original_segs = list(sess.segments)
    ok = refine_segments(
        sess, video_path=tmp_path / "ep.mp4", work_dir=tmp_path / "w",
        provider=None, global_style="末日",
        detect=lambda v: [Shot(0, 0.0, 1.0)],
        extract_frames=lambda *a, **k: [Path("/x.png")],
        tag_fn=lambda paths: EmotionTag())
    assert ok is False
    assert sess.segments == original_segs
    assert sess.segments[0].music_prompt == "Instrumental tense"
