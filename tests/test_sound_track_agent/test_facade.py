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


from sound_track_agent.facade import advance
from sound_track_agent.pipeline import Stages
from sound_track_agent.session import SegmentScore, EmotionTag, BGMCandidate


def _sess(tmp_path):
    return ScoringSession(
        source_mp4=str(tmp_path / "ep.mp4"), source_hash="h",
        global_style="末日废土", frame_rate=24.0,
        segments=[SegmentScore(index=0, t_start=0.0, t_end=4.0)])


def _fake_stages():
    return Stages(
        tag_emotion=lambda seg, s: EmotionTag(labels=["tense"], arousal=0.7),
        compose_prompt=lambda seg, s: f"tags-{seg.index}",
        generate=lambda seg, s: [BGMCandidate(path="/x/b.wav", seed=1, prompt="t")],
        align=lambda s: None,
        mix=lambda s: "/x/out.mp4",
    )


def test_advance_runs_with_injected_stages_and_reports_progress(tmp_path):
    sess = _sess(tmp_path)
    msgs = []
    out = advance(sess, tmp_path / "work", cfg=object(), workflow_id="wf",
                  stop_after="mix", stages=_fake_stages(),
                  on_progress=msgs.append)
    assert out.output == "/x/out.mp4"
    assert all(s.status == "aligned" for s in out.segments)
    assert len(msgs) >= 1


def test_advance_stop_after_generate_no_mix(tmp_path):
    sess = _sess(tmp_path)
    out = advance(sess, tmp_path / "work", cfg=object(), workflow_id="wf",
                  stop_after="generate", stages=_fake_stages())
    assert out.output is None
    assert all(s.status == "generated" for s in out.segments)
    assert (tmp_path / "work" / "session.json").exists()
