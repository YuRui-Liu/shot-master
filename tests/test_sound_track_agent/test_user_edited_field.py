"""SegmentScore + SFXShot 加 user_edited + disabled 字段（4c 标记）。"""
from sound_track_agent.session import SegmentScore
from sound_track_agent.sfx.session import SFXShot


def test_segment_score_has_user_edited_default_false():
    seg = SegmentScore(0, 0.0, 5.0)
    assert seg.user_edited is False


def test_segment_score_has_disabled_default_false():
    """4c DeleteCue 软删 BGM 需要 disabled 字段。"""
    seg = SegmentScore(0, 0.0, 5.0)
    assert seg.disabled is False


def test_sfx_shot_has_user_edited_default_false():
    shot = SFXShot(0, 0.0, 3.0)
    assert shot.user_edited is False


def test_segment_score_roundtrip_preserves_user_edited_and_disabled(tmp_path):
    from sound_track_agent.session import ScoringSession
    sess = ScoringSession(source_mp4="/a.mp4", source_hash="h",
                          global_style="x", frame_rate=24.0,
                          segments=[SegmentScore(0, 0.0, 5.0, user_edited=True, disabled=True)])
    p = tmp_path / "session.json"
    sess.save(p)
    loaded = ScoringSession.load(p)
    assert loaded is not None
    assert loaded.segments[0].user_edited is True
    assert loaded.segments[0].disabled is True


def test_sfx_shot_roundtrip_preserves_user_edited(tmp_path):
    from sound_track_agent.sfx.session import SFXSession
    sess = SFXSession(source_mp4="/a.mp4", source_hash="h", frame_rate=24.0,
                      shots=[SFXShot(0, 0.0, 3.0, user_edited=True)])
    p = tmp_path / "sfx_session.json"
    sess.save(p)
    loaded = SFXSession.load(p)
    assert loaded is not None
    assert loaded.shots[0].user_edited is True
