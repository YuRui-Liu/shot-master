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


from sound_track_agent.facade import _make_align_fn
from sound_track_agent.session import AccentPoint


def test_align_fn_fills_accents_when_empty(monkeypatch):
    import sound_track_agent.accent_detector as ad
    monkeypatch.setattr(ad, "detect_accents",
                        lambda v, **k: [AccentPoint(t=1.0, intensity=0.9)])
    sess = ScoringSession(source_mp4="/x/ep.mp4", source_hash="h",
                          global_style="s", frame_rate=24.0,
                          segments=[SegmentScore(index=0, t_start=0.0, t_end=4.0)])
    _make_align_fn("/x/ep.mp4")(sess)
    assert len(sess.accent_points) == 1
    assert sess.accent_points[0].t == 1.0


def test_align_fn_skips_when_accents_exist(monkeypatch):
    import sound_track_agent.accent_detector as ad
    monkeypatch.setattr(ad, "detect_accents",
                        lambda v, **k: [AccentPoint(t=9.9, intensity=1.0)])
    sess = ScoringSession(source_mp4="/x/ep.mp4", source_hash="h",
                          global_style="s", frame_rate=24.0,
                          segments=[SegmentScore(index=0, t_start=0.0, t_end=4.0)],
                          accent_points=[AccentPoint(t=2.0, intensity=0.5)])
    _make_align_fn("/x/ep.mp4")(sess)
    # 已有不覆盖
    assert len(sess.accent_points) == 1
    assert sess.accent_points[0].t == 2.0


def test_build_accent_preview_outputs_wav(tmp_path):
    import numpy as np, soundfile as sf
    from sound_track_agent import facade
    from sound_track_agent.session import (
        ScoringSession, SegmentScore, BGMCandidate, AccentPoint)

    def _tone(p, f, dur=1.0, sr=22050):
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        sf.write(str(p), (0.3 * np.sin(2 * np.pi * f * t)).astype(np.float32), sr)

    b0 = tmp_path / "b0.wav"; _tone(b0, 440)
    b1 = tmp_path / "b1.wav"; _tone(b1, 550)
    sess = ScoringSession(
        source_mp4="x", source_hash="h", global_style="g", frame_rate=24.0,
        segments=[
            SegmentScore(index=0, t_start=0.0, t_end=1.0,
                         candidates=[BGMCandidate(path=str(b0), seed=1, prompt="t")],
                         chosen_candidate=0),
            SegmentScore(index=1, t_start=1.0, t_end=2.0,
                         candidates=[BGMCandidate(path=str(b1), seed=1, prompt="t")],
                         chosen_candidate=None)],   # 未选 → 用候选0
        accent_points=[AccentPoint(t=0.5, intensity=0.9)])
    out = facade.build_accent_preview(sess, tmp_path / "w", crossfade=0.1)
    from pathlib import Path
    assert Path(out).exists() and Path(out).stat().st_size > 0


def test_build_accent_preview_disabled_still_outputs(tmp_path):
    import numpy as np, soundfile as sf
    from sound_track_agent import facade
    from sound_track_agent.session import (
        ScoringSession, SegmentScore, BGMCandidate)

    def _tone(p, f, dur=1.0, sr=22050):
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        sf.write(str(p), (0.3 * np.sin(2 * np.pi * f * t)).astype(np.float32), sr)

    b0 = tmp_path / "b0.wav"; _tone(b0, 440)
    sess = ScoringSession(
        source_mp4="x", source_hash="h", global_style="g", frame_rate=24.0,
        segments=[SegmentScore(index=0, t_start=0.0, t_end=1.0,
                  candidates=[BGMCandidate(path=str(b0), seed=1, prompt="t")],
                  chosen_candidate=0)])
    sess.accent_mix_enabled = False
    out = facade.build_accent_preview(sess, tmp_path / "w2", crossfade=0.1)
    from pathlib import Path
    assert Path(out).exists()


import threading

from sound_track_agent import facade
from sound_track_agent.pipeline import Stages
from sound_track_agent.scorer import CandidateScore
from sound_track_agent.session import ScoringSession, SegmentScore, BGMCandidate


class _Cfg:
    runninghub_api_key = "k"
    runninghub_base_url = "https://example.test"
    soundtrack_max_concurrency = 2
    soundtrack_score_weights = None


class _FakeClient:
    def __init__(self):
        self.created = []
        self._lock = threading.Lock()

    def create_task(self, *, workflow_id, node_info_list=None):
        seed = next(n["fieldValue"] for n in node_info_list if n["nodeId"] == "109")
        with self._lock:
            self.created.append(seed)
        return f"t{seed}"

    def query_task(self, task_id):
        return {"status": "SUCCESS", "results": [{"url": "http://x/a.mp3"}]}

    def download_file(self, url, dest):
        from pathlib import Path
        dest = Path(dest); dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"A")
        return dest


def _one_seg_session():
    return ScoringSession(
        source_mp4="x", source_hash="h", global_style="style", frame_rate=24.0,
        segments=[SegmentScore(index=0, t_start=0.0, t_end=1.0, next_seed=3,
                               status="generated")])


def test_regenerate_uses_injected_client_and_fresh_seeds(tmp_path):
    sess = _one_seg_session()
    client = _FakeClient()
    facade.regenerate_segment(
        sess, 0, tmp_path, cfg=_Cfg(), workflow_id="wf", seeds_count=2,
        client=client,
        score_fn=lambda p, expected_dur=0.0: CandidateScore(0.5, 1.0, 0.5, 0.5))
    seg = sess.segments[0]
    assert sorted(client.created) == [3, 4]          # 用 next_seed 起的新种子
    assert seg.next_seed == 5
    assert len(seg.candidates) == 2 and seg.chosen_candidate is not None
    assert (tmp_path / "session.json").exists()       # 落盘


def test_regenerate_seg_index_out_of_range_raises(tmp_path):
    import pytest
    sess = _one_seg_session()
    with pytest.raises(ValueError):
        facade.regenerate_segment(sess, 5, tmp_path, cfg=_Cfg(),
                                  workflow_id="wf", client=_FakeClient())


def test_regenerate_does_not_touch_other_segments(tmp_path):
    sess = ScoringSession(
        source_mp4="x", source_hash="h", global_style="style", frame_rate=24.0,
        segments=[
            SegmentScore(index=0, t_start=0.0, t_end=1.0, next_seed=1,
                         status="generated",
                         candidates=[BGMCandidate(path="/old0.wav", seed=1, prompt="t")],
                         chosen_candidate=0),
            SegmentScore(index=1, t_start=1.0, t_end=2.0, next_seed=3,
                         status="generated",
                         candidates=[BGMCandidate(path="/old1.wav", seed=1, prompt="t")],
                         chosen_candidate=0)])
    client = _FakeClient()
    facade.regenerate_segment(
        sess, 1, tmp_path, cfg=_Cfg(), workflow_id="wf", seeds_count=2,
        client=client,
        score_fn=lambda p, expected_dur=0.0: CandidateScore(0.5, 1.0, 0.5, 0.5))
    # 段 0 不被动
    assert sess.segments[0].candidates[0].path == "/old0.wav"
    assert sess.segments[0].chosen_candidate == 0
    assert sess.segments[0].next_seed == 1
    # 段 1 被新种子替换
    assert sorted(client.created) == [3, 4]
    assert sess.segments[1].next_seed == 5


def test_advance_preserves_generate_all_under_progress(tmp_path):
    # progress 包装（on_progress 非 None）后，generate_all 钩子不能丢，否则回退到逐段
    sess = ScoringSession(source_mp4="x", source_hash="h", global_style="s",
                          frame_rate=24.0,
                          segments=[SegmentScore(index=0, t_start=0.0, t_end=1.0,
                                                 status="prompted")])
    calls = {"all": 0}

    def gen_all(s):
        calls["all"] += 1
        s.segments[0].candidates = [BGMCandidate(path="a.mp3", seed=1, prompt="p")]
        s.segments[0].chosen_candidate = 0

    stages = Stages(
        tag_emotion=lambda seg, s: None,
        compose_prompt=lambda seg, s: "p",
        generate=lambda seg, s: (_ for _ in ()).throw(AssertionError("不应走逐段")),
        align=lambda s: None, mix=lambda s: "out.mp4",
        generate_all=gen_all)
    facade.advance(sess, tmp_path / "w", cfg=object(), workflow_id="wf",
                   stop_after="generate", stages=stages, on_progress=lambda m: None)
    assert calls["all"] == 1
    assert sess.segments[0].status == "generated"


def test_regenerate_total_failure_restores_state_but_advances_seed(tmp_path):
    """全 job 失败：候选/chosen/status 回滚；next_seed 仍推进（防卡死）。"""
    class FailClient(_FakeClient):
        def query_task(self, task_id):
            return {"status": "FAILED", "errorMessage": "boom"}

    sess = ScoringSession(
        source_mp4="x", source_hash="h", global_style="style", frame_rate=24.0,
        segments=[SegmentScore(index=0, t_start=0.0, t_end=1.0, next_seed=3,
                               status="generated",
                               candidates=[BGMCandidate(path="/old.wav",
                                                        seed=1, prompt="t")],
                               chosen_candidate=0)])
    facade.regenerate_segment(
        sess, 0, tmp_path, cfg=_Cfg(), workflow_id="wf", seeds_count=2,
        client=FailClient(),
        score_fn=lambda p, expected_dur=0.0: CandidateScore(0.5, 1.0, 0.5, 0.5))
    seg = sess.segments[0]
    # 旧候选/chosen/status 保留
    assert len(seg.candidates) == 1 and seg.candidates[0].path == "/old.wav"
    assert seg.chosen_candidate == 0
    assert seg.status == "generated"
    # next_seed 仍推进，避免下次重试卡同一种子窗口
    assert seg.next_seed == 5    # 3 -> +2


# ── Phase 2 Task 6 新增测试 ──────────────────────────────────────────────────

def test_prepare_session_accepts_and_persists_dialogue_segments(tmp_path):
    from sound_track_agent.facade import prepare_session
    from sound_track_agent.segment_planner import Shot
    from sound_track_agent.session import DialogueSegment
    mp4 = tmp_path / "ep.mp4"; mp4.write_bytes(b"f")
    segs = [DialogueSegment(audio_path="/x/a.flac", t_start=0.0, duration=1.0),
            DialogueSegment(audio_path="/x/b.flac", t_start=2.0, duration=1.0)]
    sess = prepare_session(mp4, "末日", tmp_path / "w",
                           dialogue_segments=segs,
                           detect=lambda p: [Shot(0, 0.0, 3.0)])
    assert len(sess.dialogue_segments) == 2
    assert sess.dialogue_segments[1].audio_path == "/x/b.flac"


def test_advance_overrides_dialogue_segments_when_provided(tmp_path):
    """advance 传 dialogue_segments 非空时覆盖 session；空/None 不动。"""
    from sound_track_agent.facade import advance
    from sound_track_agent.pipeline import Stages
    from sound_track_agent.session import (
        ScoringSession, SegmentScore, EmotionTag, BGMCandidate, DialogueSegment,
    )
    sess = ScoringSession(
        source_mp4="x", source_hash="h", global_style="s", frame_rate=24.0,
        segments=[SegmentScore(index=0, t_start=0.0, t_end=2.0)],
        dialogue_segments=[DialogueSegment(
            audio_path="/old.flac", t_start=0.0, duration=1.0)])
    fake = Stages(
        tag_emotion=lambda seg, s: EmotionTag(labels=["x"]),
        compose_prompt=lambda seg, s: "p",
        generate=lambda seg, s: [BGMCandidate(path="/b.wav", seed=1, prompt="t")],
        align=lambda s: None, mix=lambda s: "/out.mp4")
    new_segs = [DialogueSegment(audio_path="/new.flac", t_start=0.5, duration=2.0)]
    advance(sess, tmp_path / "w", cfg=object(), workflow_id="wf",
            stop_after="mix", stages=fake, dialogue_segments=new_segs)
    assert sess.dialogue_segments[0].audio_path == "/new.flac"


def test_build_accent_preview_invokes_align_with_pump_skip(tmp_path, monkeypatch):
    """预览路径与 mix 路径共用 align+pump 流程：monkeypatch align 返回固定
    aligned set，断言 align 被调用且预览 wav 正常产出。"""
    import numpy as np, soundfile as sf
    from pathlib import Path
    from sound_track_agent import facade
    import sound_track_agent.beat_aligner as ba
    from sound_track_agent.session import (
        ScoringSession, SegmentScore, BGMCandidate, AccentPoint)

    def _tone(p, f, dur=1.0, sr=22050):
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        sf.write(str(p), (0.3 * np.sin(2 * np.pi * f * t)).astype(np.float32), sr)

    b0 = tmp_path / "b0.wav"; _tone(b0, 440)
    b1 = tmp_path / "b1.wav"; _tone(b1, 550)
    sess = ScoringSession(
        source_mp4="x", source_hash="h", global_style="g", frame_rate=24.0,
        segments=[
            SegmentScore(index=0, t_start=0.0, t_end=1.0,
                         candidates=[BGMCandidate(path=str(b0), seed=1, prompt="t")],
                         chosen_candidate=0),
            SegmentScore(index=1, t_start=1.0, t_end=2.0,
                         candidates=[BGMCandidate(path=str(b1), seed=1, prompt="t")],
                         chosen_candidate=0)],
        accent_points=[AccentPoint(t=0.5, intensity=0.9)])

    align_called = {"flag": False}

    def fake_align(bgm, accents, *, max_stretch, big_threshold, out_path):
        align_called["flag"] = True
        return Path(bgm), frozenset({0})

    monkeypatch.setattr(ba, "align_beats_to_accents", fake_align)
    out = facade.build_accent_preview(sess, tmp_path / "w", crossfade=0.1)
    assert Path(out).exists() and Path(out).stat().st_size > 0
    assert align_called["flag"] is True
