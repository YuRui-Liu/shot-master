from pathlib import Path
from sound_track_agent.session import (
    ScoringSession, SegmentScore, EmotionTag, BGMCandidate,
)
from sound_track_agent.pipeline import Stages, run


def _base_session():
    return ScoringSession(
        source_mp4="/x/ep1.mp4", source_hash="h1",
        global_style="冷色调", frame_rate=24.0,
        segments=[SegmentScore(index=0, t_start=0.0, t_end=4.0),
                  SegmentScore(index=1, t_start=4.0, t_end=8.0)],
    )


def _stub_stages():
    return Stages(
        tag_emotion=lambda seg, sess: EmotionTag(labels=["calm"], arousal=0.2),
        compose_prompt=lambda seg, sess: f"prompt-{seg.index}",
        generate=lambda seg, sess: [
            BGMCandidate(path=f"/x/{seg.index}.wav", seed=1,
                         prompt=seg.music_prompt)],
        align=lambda sess: None,
        mix=lambda sess: "/x/out.mp4",
    )


def test_run_advances_all_segments_to_generated(tmp_path):
    sess = _base_session()
    sp = tmp_path / "session.json"
    run(sess, _stub_stages(), session_path=sp, stop_after="generate")
    assert all(s.status == "generated" for s in sess.segments)
    assert all(s.emotion is not None for s in sess.segments)
    assert all(s.music_prompt == f"prompt-{s.index}" for s in sess.segments)
    assert all(len(s.candidates) == 1 for s in sess.segments)
    assert sp.exists()


def test_run_stop_after_tag_does_not_generate(tmp_path):
    sess = _base_session()
    run(sess, _stub_stages(), session_path=tmp_path / "s.json",
        stop_after="tag_emotion")
    assert all(s.status == "tagged" for s in sess.segments)
    assert all(s.music_prompt == "" for s in sess.segments)


def test_run_resumes_from_persisted_state(tmp_path):
    sess = _base_session()
    sp = tmp_path / "s.json"
    run(sess, _stub_stages(), session_path=sp, stop_after="tag_emotion")
    reloaded = ScoringSession.load(sp)
    out = run(reloaded, _stub_stages(), session_path=sp, stop_after="mix")
    assert out == "/x/out.mp4"
    assert reloaded.output == "/x/out.mp4"
    assert all(s.status == "aligned" for s in reloaded.segments)
