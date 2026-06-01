"""media_agent 配乐 DAW 端点 — 零 Qt、零网络、零 ffmpeg/cv2/demucs。

advance/mixdown/accent/sfx/overlay 全部通过模块级可注入工厂换成假实现：
- advance → 注入假 pipeline.Stages（不触 provider/RunningHub/mixdown）。
- mixdown → 注入假 I/O（assemble_bgm/extract_audio/separate/duck/replace_video）。
- accent/detect → 注入假 detect（不触 cv2 光流）；accent/mix → 真实纯算法（soundfile）。
- sfx/detect → monkeypatch shot_detector + 注入假 provider；sfx/generate → 注入假 client。
- overlay → 注入假 client（generate_overlay_clip 用其下载，落 audio_cache）。
"""
from pathlib import Path

import media_agent.routes.soundtrack as st_mod
from fastapi.testclient import TestClient

from media_agent.server import create_app
from sound_track_agent.session import (
    ScoringSession, SegmentScore, BGMCandidate, AccentPoint, EmotionTag)
from sound_track_agent.pipeline import Stages

client = TestClient(create_app())


# ---------------------------------------------------------------------------
# 公共 helpers
# ---------------------------------------------------------------------------

def _make_session(work_dir: Path, *, status="generated", n=2):
    """造一个已推进到 status 的 ScoringSession + 段落候选 wav，落盘 session.json。"""
    work_dir.mkdir(parents=True, exist_ok=True)
    mp4 = work_dir / "src.mp4"
    mp4.write_bytes(b"FAKE_MP4")
    segs = []
    for i in range(n):
        cand_path = work_dir / f"seg{i}.wav"
        cand_path.write_bytes(b"FAKE_WAV")
        segs.append(SegmentScore(
            index=i, t_start=float(i * 10), t_end=float(i * 10 + 10),
            music_prompt=f"prompt {i}",
            candidates=[BGMCandidate(path=str(cand_path), seed=1, prompt="p")],
            chosen_candidate=0, status=status,
            emotion=EmotionTag(labels=["calm"])))
    sess = ScoringSession(source_mp4=str(mp4), source_hash="h",
                          global_style="cinematic", frame_rate=24.0,
                          segments=segs)
    sess.save(work_dir / "session.json")
    return sess


def _fake_stages() -> Stages:
    """假 Stages：纯内存推进，不触任何外部依赖。mix 写一个假成片文件。"""
    out_holder = {}

    def tag(seg, sess):
        return EmotionTag(labels=["tagged"])

    def prompt(seg, sess):
        return f"composed {seg.index}"

    def gen(seg, sess):
        return [BGMCandidate(path="fake.wav", seed=1, prompt="x")]

    def align(sess):
        sess.accent_points = [AccentPoint(t=1.0, intensity=0.9)]

    def mix(sess):
        out = Path(sess.source_mp4).with_name("out_scored.mp4")
        out.write_bytes(b"SCORED")
        out_holder["out"] = str(out)
        return str(out)

    return Stages(tag_emotion=tag, compose_prompt=prompt, generate=gen,
                  align=align, mix=mix)


# ===========================================================================
# advance
# ===========================================================================

def test_advance_uses_injected_stages(tmp_path, monkeypatch):
    wd = tmp_path / "wd"
    _make_session(wd, status="pending", n=2)
    monkeypatch.setattr(st_mod, "_load_cfg", lambda: object())
    monkeypatch.setattr(st_mod, "_stages_factory",
                        lambda *a, **k: _fake_stages())
    r = client.post("/soundtrack/advance", json={
        "work_dir": str(wd), "workflow_id": "wf", "stop_after": "mix"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["output"] and body["output"].endswith("out_scored.mp4")
    assert Path(body["output"]).read_bytes() == b"SCORED"
    assert len(body["segments"]) == 2
    # mix 后段落推进到 aligned，且 accents 已填
    assert body["accents"] and body["accents"][0]["t"] == 1.0


def test_advance_stop_after_intermediate(tmp_path, monkeypatch):
    wd = tmp_path / "wd2"
    _make_session(wd, status="pending", n=1)
    monkeypatch.setattr(st_mod, "_load_cfg", lambda: object())
    monkeypatch.setattr(st_mod, "_stages_factory",
                        lambda *a, **k: _fake_stages())
    r = client.post("/soundtrack/advance", json={
        "work_dir": str(wd), "workflow_id": "wf", "stop_after": "compose_prompt"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["output"] is None
    assert body["segments"][0]["status"] == "prompted"


def test_advance_no_session_no_video_400(tmp_path, monkeypatch):
    monkeypatch.setattr(st_mod, "_load_cfg", lambda: object())
    r = client.post("/soundtrack/advance", json={
        "work_dir": str(tmp_path / "empty"), "workflow_id": "wf"})
    assert r.status_code == 400


def test_advance_prepares_session_from_video(tmp_path, monkeypatch):
    wd = tmp_path / "wd3"
    wd.mkdir()
    mp4 = wd / "v.mp4"
    mp4.write_bytes(b"FAKE")
    # 注入假 prepare_session 避免触 PySceneDetect/cv2
    fake = ScoringSession(source_mp4=str(mp4), source_hash="h",
                          global_style="noir", frame_rate=24.0,
                          segments=[SegmentScore(index=0, t_start=0, t_end=5,
                                                 status="pending")])
    monkeypatch.setattr(st_mod._facade, "prepare_session",
                        lambda *a, **k: fake)
    monkeypatch.setattr(st_mod, "_load_cfg", lambda: object())
    monkeypatch.setattr(st_mod, "_stages_factory",
                        lambda *a, **k: _fake_stages())
    r = client.post("/soundtrack/advance", json={
        "work_dir": str(wd), "video": str(mp4), "global_style": "noir",
        "workflow_id": "wf", "stop_after": "tag_emotion"})
    assert r.status_code == 200, r.text
    assert r.json()["global_style"] == "noir"


# ===========================================================================
# mixdown
# ===========================================================================

def test_mixdown_with_fake_io(tmp_path, monkeypatch):
    wd = tmp_path / "mix"
    sess = _make_session(wd, status="generated", n=2)

    def fake_assemble_bgm(seg_bgms, out, **kw):
        Path(out).write_bytes(b"BGM")
        return Path(out)

    def fake_extract_audio(video, out):
        Path(out).write_bytes(b"AUD")
        return Path(out)

    def fake_separate(src, out_dir):
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        v = Path(out_dir) / "vocals.wav"
        v.write_bytes(b"V")
        return v, Path(out_dir) / "rest.wav"

    def fake_duck(vocals, bgm, out, **kw):
        Path(out).write_bytes(b"MIX")
        return Path(out)

    def fake_replace(video, mixed, out_video):
        Path(out_video).write_bytes(b"FINAL")
        return Path(out_video)

    monkeypatch.setattr(st_mod, "_load_cfg", lambda: object())
    monkeypatch.setattr(st_mod, "_mixdown_io_factory", lambda: {
        "assemble_bgm_fn": fake_assemble_bgm,
        "extract_audio_fn": fake_extract_audio,
        "separate": fake_separate,
        "duck_and_mix_fn": fake_duck,
        "replace_video_audio_fn": fake_replace,
        "duration_of": lambda v: 20.0,
    })
    r = client.post("/soundtrack/mixdown", json={"work_dir": str(wd)})
    assert r.status_code == 200, r.text
    out = r.json()["output"]
    assert Path(out).read_bytes() == b"FINAL"
    # 写回 session.output
    reloaded = ScoringSession.load(wd / "session.json")
    assert reloaded.output == out


def test_mixdown_no_session_400(tmp_path, monkeypatch):
    monkeypatch.setattr(st_mod, "_load_cfg", lambda: object())
    r = client.post("/soundtrack/mixdown", json={
        "work_dir": str(tmp_path / "none")})
    assert r.status_code == 400


# ===========================================================================
# accent
# ===========================================================================

def test_accent_detect_injected(tmp_path, monkeypatch):
    wd = tmp_path / "acc"
    _make_session(wd, status="generated", n=2)
    monkeypatch.setattr(
        st_mod, "_accent_detector",
        lambda video, **kw: [AccentPoint(t=2.0, intensity=0.8),
                             AccentPoint(t=5.0, intensity=0.5)])
    r = client.post("/soundtrack/accent/detect", json={
        "video": str(wd / "src.mp4"), "work_dir": str(wd)})
    assert r.status_code == 200, r.text
    accents = r.json()["accents"]
    assert len(accents) == 2 and accents[0]["t"] == 2.0
    # 写回 session
    reloaded = ScoringSession.load(wd / "session.json")
    assert len(reloaded.accent_points) == 2


def test_accent_detect_no_workdir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        st_mod, "_accent_detector",
        lambda video, **kw: [AccentPoint(t=1.0, intensity=0.9)])
    r = client.post("/soundtrack/accent/detect", json={"video": "x.mp4"})
    assert r.status_code == 200
    assert r.json()["accents"][0]["intensity"] == 0.9


def test_accent_mix_real_algorithm(tmp_path, monkeypatch):
    """accent/mix 走真实 facade.build_accent_preview，注入假 assemble_bgm 避免 ffmpeg。

    无 accent_points → 仅拼接路径（不触 align/pump），验证返回 wav 路径。
    """
    wd = tmp_path / "amix"
    _make_session(wd, status="generated", n=2)  # 无 accent_points → 拼接分支
    monkeypatch.setattr(st_mod, "_load_cfg", lambda: object())

    import sound_track_agent.bgm_assembler as bgm_asm

    def fake_assemble(seg_bgms, out, **kw):
        Path(out).write_bytes(b"PREVIEW")
        return str(out)

    monkeypatch.setattr(bgm_asm, "assemble_bgm", fake_assemble)
    r = client.post("/soundtrack/accent/mix", json={"work_dir": str(wd)})
    assert r.status_code == 200, r.text
    out = r.json()["preview"]
    assert Path(out).exists()


def test_accent_mix_no_session_400(tmp_path, monkeypatch):
    monkeypatch.setattr(st_mod, "_load_cfg", lambda: object())
    r = client.post("/soundtrack/accent/mix", json={
        "work_dir": str(tmp_path / "none")})
    assert r.status_code == 400


# ===========================================================================
# sfx
# ===========================================================================

class _FakeProvider:
    """假 vision provider：始终判定需要 SFX。"""
    def generate(self, frames, sys, usr):
        return '{"needs_sfx": true, "prompt_short": "门吱呀", "duration_hint": 3.0}'


class _FakeRHClient:
    def create_task(self, *, workflow_id, node_info_list=None, **kw):
        return "task-1"

    def query_task(self, task_id):
        return {"status": "SUCCESS", "results": [{"url": "http://x/sfx.mp3"}]}

    def download_file(self, url, dest):
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"FAKE_SFX")
        return dest


def _patch_sfx_shots(monkeypatch):
    """monkeypatch shot_detector.detect_shots，避开 PySceneDetect/cv2。"""
    from sound_track_agent.segment_planner import Shot
    import sound_track_agent.shot_detector as sd
    monkeypatch.setattr(sd, "detect_shots",
                        lambda mp4, **kw: [Shot(index=0, t_start=0.0, t_end=4.0)])


def test_sfx_detect_and_generate(tmp_path, monkeypatch):
    wd = tmp_path / "sfx"
    wd.mkdir()
    mp4 = wd / "v.mp4"
    mp4.write_bytes(b"FAKE")
    _patch_sfx_shots(monkeypatch)
    # 帧抽取注入：返回一个假帧路径，使 plan_one_shot 进 LLM 分支
    import sound_track_agent.sfx.facade as sfx_facade
    frame = wd / "f.png"
    frame.write_bytes(b"PNG")
    monkeypatch.setattr(sfx_facade, "_extract_frames_for_shot",
                        lambda mp4_path, shot, n: [frame])
    monkeypatch.setattr(st_mod, "_load_cfg", lambda: object())
    monkeypatch.setattr(st_mod, "_sfx_provider_factory",
                        lambda cfg: _FakeProvider())
    monkeypatch.setattr(st_mod, "_sfx_client_factory",
                        lambda cfg: _FakeRHClient())

    r = client.post("/soundtrack/sfx/detect", json={
        "video": str(mp4), "work_dir": str(wd)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sfx_planned"] is True
    assert body["shots"][0]["status"] == "planned"
    assert body["shots"][0]["prompt_short"] == "门吱呀"

    g = client.post("/soundtrack/sfx/generate", json={"work_dir": str(wd)})
    assert g.status_code == 200, g.text
    gb = g.json()
    assert gb["shots"][0]["status"] == "generated"
    assert gb["shots"][0]["n_candidates"] >= 1


def test_sfx_generate_no_session_400(tmp_path, monkeypatch):
    monkeypatch.setattr(st_mod, "_load_cfg", lambda: object())
    r = client.post("/soundtrack/sfx/generate", json={
        "work_dir": str(tmp_path / "none")})
    assert r.status_code == 400


# ===========================================================================
# overlay
# ===========================================================================

class _FakeOverlayClient:
    def create_task(self, *, workflow_id, node_info_list=None, **kw):
        return "task-ov"

    def query_task(self, task_id):
        return {"status": "SUCCESS", "results": [{"url": "http://x/ov.mp3"}]}

    def download_file(self, url, dest):
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"FAKE_OVERLAY")
        return dest


def test_overlay_generate_list_remove(tmp_path, monkeypatch):
    wd = tmp_path / "ov"
    wd.mkdir()
    monkeypatch.setattr(st_mod, "_load_cfg", lambda: object())
    monkeypatch.setattr(st_mod, "_overlay_client_factory",
                        lambda cfg: _FakeOverlayClient())

    r = client.post("/soundtrack/overlay/generate", json={
        "work_dir": str(wd), "kind": "bgm", "prompt": "tense strings",
        "t_start": 2.0, "t_end": 8.0, "seg_id": "ov1"})
    assert r.status_code == 200, r.text
    seg = r.json()["segment"]
    assert seg["id"] == "ov1" and seg["kind"] == "bgm"
    assert seg["audio_path"] and Path(seg["audio_path"]).exists()

    lst = client.post("/soundtrack/overlay/list", json={"work_dir": str(wd)})
    assert lst.status_code == 200
    assert len(lst.json()["segments"]) == 1

    rm = client.post("/soundtrack/overlay/remove", json={
        "work_dir": str(wd), "seg_id": "ov1"})
    assert rm.status_code == 200
    assert rm.json()["segments"] == []


def test_overlay_generate_bad_kind_400(tmp_path, monkeypatch):
    monkeypatch.setattr(st_mod, "_load_cfg", lambda: object())
    r = client.post("/soundtrack/overlay/generate", json={
        "work_dir": str(tmp_path), "kind": "video", "prompt": "x",
        "t_start": 0.0, "t_end": 1.0})
    assert r.status_code == 400


def test_overlay_generate_bad_range_400(tmp_path, monkeypatch):
    monkeypatch.setattr(st_mod, "_load_cfg", lambda: object())
    r = client.post("/soundtrack/overlay/generate", json={
        "work_dir": str(tmp_path), "kind": "bgm", "prompt": "x",
        "t_start": 5.0, "t_end": 2.0})
    assert r.status_code == 400


def test_overlay_remove_not_found_404(tmp_path, monkeypatch):
    wd = tmp_path / "ov2"
    wd.mkdir()
    r = client.post("/soundtrack/overlay/remove", json={
        "work_dir": str(wd), "seg_id": "nope"})
    assert r.status_code == 404
