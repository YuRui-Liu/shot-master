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


def _prompted_session(n=2):
    segs = [SegmentScore(index=i, t_start=float(i), t_end=float(i) + 1.0,
                         status="prompted") for i in range(n)]
    return ScoringSession(source_mp4="x", source_hash="h", global_style="s",
                          frame_rate=24.0, segments=segs)


def _base_stage_fns():
    return dict(
        tag_emotion=lambda seg, s: EmotionTag(),
        compose_prompt=lambda seg, s: "p",
        generate=lambda seg, s: [BGMCandidate(path="g.mp3", seed=1, prompt="p")],
        align=lambda s: None,
        mix=lambda s: "out.mp4",
    )


def test_generate_all_hook_used_when_present():
    sess = _prompted_session(2)
    calls = {"all": 0, "per_seg": 0}

    def gen_all(s):
        calls["all"] += 1
        for seg in s.segments:
            seg.candidates = [BGMCandidate(path=f"seg{seg.index}.mp3", seed=seg.next_seed,
                                           prompt="p", score=0.5)]
            seg.chosen_candidate = 0

    def per_seg(seg, s):
        calls["per_seg"] += 1
        return []

    fns = _base_stage_fns(); fns["generate"] = per_seg
    stages = Stages(generate_all=gen_all, **fns)
    run(sess, stages, stop_after="generate")
    assert calls["all"] == 1 and calls["per_seg"] == 0
    assert all(seg.status == "generated" for seg in sess.segments)
    assert all(seg.candidates for seg in sess.segments)


def test_generate_all_zero_candidates_stays_prompted():
    sess = _prompted_session(2)

    def gen_all(s):
        s.segments[0].candidates = [BGMCandidate(path="a.mp3", seed=1, prompt="p")]
        # 段1 全失败：不填候选
    stages = Stages(generate_all=gen_all, **_base_stage_fns())
    run(sess, stages, stop_after="generate")
    assert sess.segments[0].status == "generated"
    assert sess.segments[1].status == "prompted"     # 0 候选留待续跑


def test_fallback_per_segment_when_no_hook():
    sess = _prompted_session(2)
    stages = Stages(**_base_stage_fns())             # generate_all 缺省 None
    run(sess, stages, stop_after="generate")
    assert all(seg.status == "generated" for seg in sess.segments)
    assert all(seg.candidates for seg in sess.segments)


def test_refine_segments_stage_runs_on_first_advance():
    """注入的 refine_segments 返回 True → segments_refined=True。"""
    sess = ScoringSession(source_mp4="x", source_hash="h", global_style="s",
                          frame_rate=24.0,
                          segments=[SegmentScore(index=0, t_start=0.0, t_end=2.0)])
    calls = {"refine": 0}

    def fake_refine(s):
        calls["refine"] += 1
        return True

    fns = _base_stage_fns()
    stages = Stages(refine_segments=fake_refine, **fns)
    run(sess, stages, stop_after="refine_segments")
    assert calls["refine"] == 1
    assert sess.segments_refined is True


def test_refine_segments_skipped_when_already_refined():
    sess = ScoringSession(source_mp4="x", source_hash="h", global_style="s",
                          frame_rate=24.0,
                          segments=[SegmentScore(index=0, t_start=0.0, t_end=2.0)])
    sess.segments_refined = True
    calls = {"refine": 0}
    fns = _base_stage_fns()

    def fake_refine(s):
        calls["refine"] += 1
        return True

    stages = Stages(refine_segments=fake_refine, **fns)
    run(sess, stages, stop_after="refine_segments")
    assert calls["refine"] == 0


def test_refine_failure_does_not_set_flag():
    sess = ScoringSession(source_mp4="x", source_hash="h", global_style="s",
                          frame_rate=24.0,
                          segments=[SegmentScore(index=0, t_start=0.0, t_end=2.0)])
    fns = _base_stage_fns()
    stages = Stages(refine_segments=lambda s: False, **fns)
    run(sess, stages, stop_after="refine_segments")
    assert sess.segments_refined is False


def test_refine_segments_default_none_no_op():
    """缺省 refine_segments=None → 现有流水线零回归。"""
    sess = ScoringSession(source_mp4="x", source_hash="h", global_style="s",
                          frame_rate=24.0,
                          segments=[SegmentScore(index=0, t_start=0.0, t_end=2.0,
                                                 status="prompted")])
    fns = _base_stage_fns()
    stages = Stages(**fns)
    run(sess, stages, stop_after="generate")
    assert sess.segments[0].status == "generated"


def test_tag_emotion_skipped_when_status_already_tagged():
    """refine 把 seg.status 置 'tagged' 后，tag_emotion stage 自然跳过（status != pending）。"""
    sess = ScoringSession(source_mp4="x", source_hash="h", global_style="s",
                          frame_rate=24.0,
                          segments=[SegmentScore(index=0, t_start=0.0, t_end=2.0,
                                                 status="tagged",
                                                 emotion=EmotionTag())])
    sess.segments_refined = True
    tag_calls = {"n": 0}
    def per_seg_tag(seg, s):
        tag_calls["n"] += 1
        return EmotionTag()
    fns = _base_stage_fns()
    fns["tag_emotion"] = per_seg_tag
    stages = Stages(**fns)
    from sound_track_agent.pipeline import run as run_pipeline
    run_pipeline(sess, stages, stop_after="tag_emotion")
    assert tag_calls["n"] == 0
