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
