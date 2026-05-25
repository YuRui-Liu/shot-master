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
