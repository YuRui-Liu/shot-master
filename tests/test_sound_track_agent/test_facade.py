from pathlib import Path
from sound_track_agent.facade import prepare_session
from sound_track_agent.segment_planner import Shot
from sound_track_agent.session import ScoringSession


def test_prepare_session_builds_segments(tmp_path):
    mp4 = tmp_path / "ep.mp4"; mp4.write_bytes(b"fakemp4")
    fake_shots = [Shot(index=0, t_start=0.0, t_end=4.0),
                  Shot(index=1, t_start=4.0, t_end=8.0)]
    sess = prepare_session(mp4, "末日废土", tmp_path / "work",
                           detect=lambda p: fake_shots)
    assert isinstance(sess, ScoringSession)
    assert sess.global_style == "末日废土"
    assert sess.source_mp4 == str(mp4)
    assert len(sess.source_hash) == 16
    assert len(sess.segments) >= 1
    assert sess.segments[0].t_start == 0.0


def test_prepare_session_frame_rate_defaults_when_unreadable(tmp_path):
    mp4 = tmp_path / "ep.mp4"; mp4.write_bytes(b"notavideo")
    sess = prepare_session(mp4, "x", tmp_path / "w",
                           detect=lambda p: [Shot(0, 0.0, 2.0)])
    assert sess.frame_rate == 24.0
