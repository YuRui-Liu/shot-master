from sound_track_agent.session import (
    EmotionTag, BGMCandidate, AccentPoint, SegmentScore, ScoringSession,
    DialogueSegment,
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


def test_bgm_candidate_score_fields_roundtrip():
    c = BGMCandidate(path="a.mp3", seed=3, prompt="p",
                     score=0.8, subscores={"health": 0.9, "headroom": 0.7, "beat": 0.5})
    d = c.to_dict()
    assert d["score"] == 0.8 and d["subscores"]["health"] == 0.9
    c2 = BGMCandidate(**d)
    assert c2.score == 0.8 and c2.subscores == {"health": 0.9, "headroom": 0.7, "beat": 0.5}


def test_bgm_candidate_defaults_when_missing():
    c = BGMCandidate(path="a.mp3", seed=1, prompt="p")
    assert c.score is None and c.subscores == {}


def test_segment_next_seed_roundtrip_and_default():
    seg = SegmentScore(index=0, t_start=0.0, t_end=2.0, next_seed=5)
    assert seg.to_dict()["next_seed"] == 5
    # 旧 json 缺字段 → 默认 1
    d = seg.to_dict(); del d["next_seed"]
    assert SegmentScore.from_dict(d).next_seed == 1


def test_session_roundtrip_preserves_new_fields(tmp_path):
    sess = ScoringSession(source_mp4="x.mp4", source_hash="h",
                          global_style="s", frame_rate=24.0,
                          segments=[SegmentScore(index=0, t_start=0.0, t_end=2.0,
                                                 next_seed=7,
                                                 candidates=[BGMCandidate(
                                                     path="b.mp3", seed=7, prompt="p",
                                                     score=0.6, subscores={"health": 1.0})])])
    p = tmp_path / "session.json"
    sess.save(p)
    back = ScoringSession.load(p)
    assert back.segments[0].next_seed == 7
    assert back.segments[0].candidates[0].score == 0.6
    assert back.segments[0].candidates[0].subscores == {"health": 1.0}


def test_from_dict_does_not_alias_subscores():
    raw = {"path": "a.mp3", "seed": 1, "prompt": "p",
           "score": 0.8, "subscores": {"health": 0.9}}
    c = BGMCandidate.from_dict(raw)
    raw["subscores"]["health"] = 0.0
    assert c.subscores["health"] == 0.9


def test_dialogue_segment_roundtrip():
    d = DialogueSegment(audio_path="/x/a.flac", t_start=1.5, duration=3.0)
    back = DialogueSegment.from_dict(d.to_dict())
    assert back.audio_path == "/x/a.flac"
    assert back.t_start == 1.5
    assert back.duration == 3.0


def test_session_dialogue_segments_roundtrip(tmp_path):
    sess = ScoringSession(
        source_mp4="x.mp4", source_hash="h", global_style="s", frame_rate=24.0,
        segments=[SegmentScore(index=0, t_start=0.0, t_end=2.0)],
        dialogue_segments=[
            DialogueSegment(audio_path="/x/d1.flac", t_start=0.0, duration=1.0),
            DialogueSegment(audio_path="/x/d2.flac", t_start=2.5, duration=0.8),
        ])
    p = tmp_path / "session.json"
    sess.save(p)
    back = ScoringSession.load(p)
    assert len(back.dialogue_segments) == 2
    assert back.dialogue_segments[0].audio_path == "/x/d1.flac"
    assert back.dialogue_segments[1].t_start == 2.5


def test_session_dialogue_segments_default_when_missing(tmp_path):
    """旧 session.json 缺字段时默认空列表（零回归）。"""
    p = tmp_path / "session.json"
    p.write_text(
        '{"source_mp4":"x","source_hash":"h","global_style":"s",'
        '"frame_rate":24.0,"segments":[],"accent_points":[]}',
        encoding="utf-8")
    back = ScoringSession.load(p)
    assert back.dialogue_segments == []


def test_segments_refined_default_false():
    sess = ScoringSession(source_mp4="x", source_hash="h", global_style="s",
                          frame_rate=24.0,
                          segments=[SegmentScore(index=0, t_start=0.0, t_end=2.0)])
    assert sess.segments_refined is False


def test_segments_refined_roundtrip(tmp_path):
    sess = ScoringSession(source_mp4="x", source_hash="h", global_style="s",
                          frame_rate=24.0,
                          segments=[SegmentScore(index=0, t_start=0.0, t_end=2.0)])
    sess.segments_refined = True
    p = tmp_path / "session.json"
    sess.save(p)
    assert ScoringSession.load(p).segments_refined is True


def test_segments_refined_default_when_missing(tmp_path):
    """旧 session.json 缺字段时默认 False（首次会触发 refine）。"""
    p = tmp_path / "session.json"
    p.write_text(
        '{"source_mp4":"x","source_hash":"h","global_style":"s",'
        '"frame_rate":24.0,"segments":[],"accent_points":[]}',
        encoding="utf-8")
    assert ScoringSession.load(p).segments_refined is False
