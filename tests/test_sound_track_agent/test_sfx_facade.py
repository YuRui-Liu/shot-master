"""sfx/facade: 集成 plan_sfx_session / generate_sfx_all / regenerate_sfx_one / set_sfx_chosen / load_sfx_session。"""
from pathlib import Path
from unittest.mock import MagicMock, patch
from sound_track_agent.sfx import facade as fac
from sound_track_agent.sfx.session import SFXSession, SFXShot, SFXCandidate


def _cfg(tmp_path):
    class _Cfg:
        sfx_workflow_id = "wf-sfx"
        sfx_plan_frames_per_shot = 3
        sfx_max_concurrency = 2
        sfx_default_volume = 0.8
        sfx_ducking_db = -6.0
        sfx_seeds_count = 1
        runninghub_api_key = ""
        runninghub_base_url = ""
    return _Cfg()


def test_plan_sfx_session_creates_from_shots(tmp_path, monkeypatch):
    """plan_sfx_session 调用 shot_detector + event_planner，落 sfx_session.json。"""
    mp4 = tmp_path / "v.mp4"; mp4.write_bytes(b"x")
    fake_shots = [
        {"index": 0, "t_start": 0.0, "t_end": 3.0, "frame_path": str(tmp_path / "f0.png")},
        {"index": 1, "t_start": 3.0, "t_end": 6.0, "frame_path": str(tmp_path / "f1.png")},
    ]
    monkeypatch.setattr(
        "sound_track_agent.sfx.facade._detect_shots",
        lambda _mp4, _cfg: fake_shots)
    monkeypatch.setattr(
        "sound_track_agent.sfx.facade._extract_frames_for_shot",
        lambda mp4, shot, n: [tmp_path / "frm.png"])
    fake_provider = MagicMock()
    fake_provider.generate.return_value = (
        '{"needs_sfx": true, "prompt_short": "门", "duration_hint": 3.0}')
    monkeypatch.setattr(
        "sound_track_agent.sfx.facade._build_provider",
        lambda _cfg: fake_provider)
    sess = fac.plan_sfx_session(str(mp4), tmp_path, cfg=_cfg(tmp_path))
    assert isinstance(sess, SFXSession)
    assert len(sess.shots) == 2
    assert all(s.status == "planned" for s in sess.shots)
    assert sess.sfx_planned is True
    # 落盘验证
    p = tmp_path / "sfx_session.json"
    assert p.exists()
    loaded = SFXSession.load(p)
    assert loaded is not None
    assert len(loaded.shots) == 2


def test_generate_sfx_all_writes_session_after(tmp_path, monkeypatch):
    sess = SFXSession("/m.mp4", "h", 24.0, shots=[
        SFXShot(0, 0.0, 3.0, prompt_short="x", duration=3.0, status="planned"),
    ])
    fake_client = MagicMock()
    fake_client.create_task.return_value = "tid"
    fake_client.query_task.return_value = {
        "status": "SUCCESS",
        "results": [{"url": "https://x/y.mp3", "outputType": "mp3"}]}
    del fake_client.get_task_status
    del fake_client.get_task_outputs
    fake_client.download_file.side_effect = lambda u, d: Path(d).write_bytes(b"a")
    monkeypatch.setattr(
        "sound_track_agent.sfx.facade._build_client",
        lambda _cfg: fake_client)
    fac.generate_sfx_all(sess, tmp_path, cfg=_cfg(tmp_path))
    assert sess.shots[0].status == "generated"
    loaded = SFXSession.load(tmp_path / "sfx_session.json")
    assert loaded.shots[0].status == "generated"


def test_regenerate_sfx_one(tmp_path, monkeypatch):
    sess = SFXSession("/m.mp4", "h", 24.0, shots=[
        SFXShot(0, 0.0, 3.0, prompt_short="x", duration=3.0,
                status="generated",
                candidates=[SFXCandidate(path="/old.mp3", seed=1, prompt="x")],
                chosen_candidate=0, next_seed=2),
    ])
    fake_client = MagicMock()
    fake_client.create_task.return_value = "tid"
    fake_client.query_task.return_value = {
        "status": "SUCCESS",
        "results": [{"url": "https://x/new.mp3", "outputType": "mp3"}]}
    del fake_client.get_task_status
    del fake_client.get_task_outputs
    fake_client.download_file.side_effect = lambda u, d: Path(d).write_bytes(b"a")
    monkeypatch.setattr(
        "sound_track_agent.sfx.facade._build_client",
        lambda _cfg: fake_client)
    fac.regenerate_sfx_one(sess, 0, tmp_path, cfg=_cfg(tmp_path))
    assert len(sess.shots[0].candidates) == 1
    # 旧的 /old.mp3 已被清空，新候选 seed 应是 next_seed=2
    assert sess.shots[0].candidates[0].seed == 2


def test_set_sfx_chosen_writes_session(tmp_path):
    sess = SFXSession("/m.mp4", "h", 24.0, shots=[
        SFXShot(0, 0.0, 3.0, status="generated",
                candidates=[
                    SFXCandidate(path="/a.mp3", seed=1, prompt="x"),
                    SFXCandidate(path="/b.mp3", seed=2, prompt="x")],
                chosen_candidate=0),
    ])
    fac.set_sfx_chosen(sess, 0, 1, work_dir=tmp_path)
    assert sess.shots[0].chosen_candidate == 1
    loaded = SFXSession.load(tmp_path / "sfx_session.json")
    assert loaded.shots[0].chosen_candidate == 1


def test_load_sfx_session_round_trip(tmp_path):
    sess = SFXSession("/m.mp4", "h", 24.0,
                      shots=[SFXShot(0, 0.0, 3.0, status="planned")])
    sess.save(tmp_path / "sfx_session.json")
    loaded = fac.load_sfx_session(tmp_path)
    assert loaded is not None
    assert loaded.shots[0].status == "planned"


def test_load_sfx_session_returns_none_when_missing(tmp_path):
    assert fac.load_sfx_session(tmp_path) is None
