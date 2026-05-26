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


from sound_track_agent.facade import load_session


def test_load_session_none_when_absent(tmp_path):
    assert load_session(tmp_path / "nope") is None


def test_load_session_roundtrip(tmp_path):
    work = tmp_path / "w"; work.mkdir()
    sess = ScoringSession(source_mp4="/x/ep.mp4", source_hash="h",
                          global_style="冷色调", frame_rate=24.0,
                          segments=[SegmentScore(index=0, t_start=0.0, t_end=4.0)])
    sess.save(work / "session.json")
    loaded = load_session(work)
    assert loaded is not None
    assert loaded.global_style == "冷色调"
    assert len(loaded.segments) == 1


from sound_track_agent.facade import set_chosen


def _seg_with_cands():
    seg = SegmentScore(index=0, t_start=0.0, t_end=4.0)
    seg.candidates = [BGMCandidate(path="/a.wav", seed=1, prompt="t"),
                      BGMCandidate(path="/b.wav", seed=2, prompt="t")]
    return ScoringSession(source_mp4="/x", source_hash="h", global_style="s",
                          frame_rate=24.0, segments=[seg])


def test_set_chosen_writes_index():
    sess = _seg_with_cands()
    set_chosen(sess, 0, 1)
    assert sess.segments[0].chosen_candidate == 1


def test_set_chosen_out_of_range_raises():
    sess = _seg_with_cands()
    import pytest
    with pytest.raises(ValueError):
        set_chosen(sess, 0, 5)
    with pytest.raises(ValueError):
        set_chosen(sess, 9, 0)


from sound_track_agent.facade import regenerate_segment


def test_regenerate_segment_replaces_only_target(tmp_path):
    s0 = SegmentScore(index=0, t_start=0.0, t_end=4.0)
    s0.candidates = [BGMCandidate(path="/old0.wav", seed=1, prompt="t")]
    s0.chosen_candidate = 0
    s1 = SegmentScore(index=1, t_start=4.0, t_end=8.0)
    s1.candidates = [BGMCandidate(path="/old1.wav", seed=1, prompt="t")]
    s1.chosen_candidate = 0
    sess = ScoringSession(source_mp4="/x", source_hash="h", global_style="s",
                          frame_rate=24.0, segments=[s0, s1])

    class _Stages:
        def __init__(self):
            self.generate = lambda seg, ss: [
                BGMCandidate(path=f"/new{seg.index}.wav", seed=9, prompt="t")]
            self.tag_emotion = self.compose_prompt = self.align = self.mix = None

    out = regenerate_segment(sess, 1, tmp_path / "w", cfg=object(),
                             workflow_id="wf", stages=_Stages())
    assert out.segments[1].candidates[0].path == "/new1.wav"
    assert out.segments[1].chosen_candidate is None
    assert out.segments[1].status == "generated"
    assert out.segments[0].candidates[0].path == "/old0.wav"
    assert out.segments[0].chosen_candidate == 0
    assert (tmp_path / "w" / "session.json").exists()


def test_regenerate_segment_out_of_range_raises(tmp_path):
    sess = ScoringSession(source_mp4="/x", source_hash="h", global_style="s",
                          frame_rate=24.0,
                          segments=[SegmentScore(index=0, t_start=0.0, t_end=4.0)])
    import pytest
    class _S:
        generate = staticmethod(lambda seg, ss: [])
    with pytest.raises(ValueError):
        regenerate_segment(sess, 9, tmp_path / "w", cfg=object(),
                           workflow_id="wf", stages=_S())
