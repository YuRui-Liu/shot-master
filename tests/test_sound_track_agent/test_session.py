from sound_track_agent.session import (
    EmotionTag, BGMCandidate, AccentPoint, SegmentScore, ScoringSession,
)


def test_segment_duration_computed():
    seg = SegmentScore(index=0, t_start=2.0, t_end=6.5)
    assert seg.duration == 4.5
    assert seg.status == "pending"
    assert seg.emotion is None
    assert seg.candidates == []


def test_session_roundtrip_to_dict_from_dict():
    sess = ScoringSession(
        source_mp4="/x/ep1.mp4", source_hash="abc123",
        global_style="末日废土冷色调", frame_rate=24.0,
        segments=[
            SegmentScore(
                index=0, t_start=0.0, t_end=8.0, shot_ids=[0, 1],
                emotion=EmotionTag(labels=["tense"], valence=-0.4,
                                   arousal=0.7, intensity=0.8),
                music_prompt="dark ambient, 90 BPM",
                candidates=[BGMCandidate(path="/x/c0.wav", seed=7,
                                         prompt="dark ambient, 90 BPM")],
                chosen_candidate=0, status="chosen",
            ),
        ],
        accent_points=[AccentPoint(t=5.2, intensity=0.9, confirmed=True)],
        output=None,
    )
    restored = ScoringSession.from_dict(sess.to_dict())
    assert restored == sess


def test_roundtrip_with_none_emotion_and_zero_chosen():
    sess = ScoringSession(
        source_mp4="/x/ep2.mp4", source_hash="h2",
        global_style="古风", frame_rate=30.0,
        segments=[
            SegmentScore(index=0, t_start=0.0, t_end=4.0),          # emotion=None
            SegmentScore(index=1, t_start=4.0, t_end=8.0,
                         candidates=[BGMCandidate(path="/x/a.wav", seed=1,
                                                  prompt="p")],
                         chosen_candidate=0),                        # 0 不能被当成"未选"
        ],
    )
    restored = ScoringSession.from_dict(sess.to_dict())
    assert restored == sess
    assert restored.segments[0].emotion is None
    assert restored.segments[1].chosen_candidate == 0


def test_to_dict_does_not_alias_emotion_labels():
    emo = EmotionTag(labels=["tense"])
    seg = SegmentScore(index=0, t_start=0.0, t_end=1.0, emotion=emo)
    d = seg.to_dict()
    d["emotion"]["labels"].append("MUTATED")
    assert emo.labels == ["tense"]      # 原实例不受序列化 dict 改动影响


from pathlib import Path
from sound_track_agent.session import hash_file


def test_hash_file_stable(tmp_path):
    f = tmp_path / "a.bin"
    f.write_bytes(b"hello world")
    h1 = hash_file(f)
    h2 = hash_file(f)
    assert h1 == h2
    assert len(h1) == 16          # 取 sha256 前 16 hex
    f.write_bytes(b"different")
    assert hash_file(f) != h1


def test_session_save_load_roundtrip(tmp_path):
    sess = ScoringSession(
        source_mp4="/x/ep1.mp4", source_hash="abc123",
        global_style="冷色调", frame_rate=24.0,
        segments=[SegmentScore(index=0, t_start=0.0, t_end=4.0)],
    )
    p = tmp_path / "session.json"
    sess.save(p)
    assert p.exists()
    loaded = ScoringSession.load(p)
    assert loaded == sess


def test_accent_mix_fields_default_and_roundtrip():
    s = ScoringSession(source_mp4="x", source_hash="h", global_style="g",
                       frame_rate=24.0)
    assert s.accent_mix_enabled is True
    assert abs(s.pump_strength - 0.6) < 1e-9
    d = s.to_dict()
    assert d["accent_mix_enabled"] is True and d["pump_strength"] == 0.6
    s2 = ScoringSession.from_dict(d)
    assert s2.accent_mix_enabled is True and s2.pump_strength == 0.6


def test_from_dict_missing_accent_mix_fields_uses_defaults():
    d = {"source_mp4": "x", "source_hash": "h", "global_style": "g",
         "frame_rate": 24.0, "segments": [], "accent_points": [], "output": None}
    s = ScoringSession.from_dict(d)
    assert s.accent_mix_enabled is True and abs(s.pump_strength - 0.6) < 1e-9


def test_segment_volume_default_and_roundtrip():
    from sound_track_agent.session import SegmentScore
    s = SegmentScore(index=0, t_start=0.0, t_end=1.0)
    assert abs(s.volume - 1.0) < 1e-9
    d = s.to_dict()
    assert d["volume"] == 1.0
    s2 = SegmentScore.from_dict(d)
    assert abs(s2.volume - 1.0) < 1e-9


def test_segment_from_dict_missing_volume_defaults():
    from sound_track_agent.session import SegmentScore
    d = {"index": 0, "t_start": 0.0, "t_end": 2.0}
    s = SegmentScore.from_dict(d)
    assert abs(s.volume - 1.0) < 1e-9
