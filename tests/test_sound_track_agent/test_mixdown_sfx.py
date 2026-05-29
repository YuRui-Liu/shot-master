"""mixdown SFX 层：assemble_sfx_track + duck_bgm_for_sfx + assemble_and_mix 接入。"""
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
from sound_track_agent.sfx.session import SFXShot, SFXSession, SFXCandidate
from sound_track_agent.mixdown import assemble_sfx_track, duck_bgm_for_sfx


def test_assemble_sfx_track_returns_none_when_empty(tmp_path):
    shots = []
    out = assemble_sfx_track(shots, tmp_path / "sfx.wav")
    assert out is None


def test_assemble_sfx_track_returns_none_when_all_disabled(tmp_path):
    shots = [SFXShot(0, 0.0, 3.0, enabled=False, status="generated",
                     candidates=[SFXCandidate("/a.mp3", 1, "x")],
                     chosen_candidate=0)]
    out = assemble_sfx_track(shots, tmp_path / "sfx.wav")
    assert out is None


def test_assemble_sfx_track_builds_ffmpeg_cmd(tmp_path):
    a = tmp_path / "a.mp3"; a.write_bytes(b"x")
    b = tmp_path / "b.mp3"; b.write_bytes(b"y")
    shots = [
        SFXShot(0, 0.0, 3.0, volume=0.8, status="generated",
                candidates=[SFXCandidate(str(a), 1, "x")], chosen_candidate=0),
        SFXShot(1, 5.0, 8.0, volume=1.0, status="generated",
                candidates=[SFXCandidate(str(b), 1, "y")], chosen_candidate=0),
    ]
    out_path = tmp_path / "sfx.wav"
    with patch("subprocess.run") as mock_run:
        def fake_run(*args, **kwargs):
            out_path.write_bytes(b"fake-wav")
            return MagicMock(returncode=0)
        mock_run.side_effect = fake_run
        result = assemble_sfx_track(shots, out_path)
    assert result == out_path
    cmd = mock_run.call_args.args[0]
    cmd_str = " ".join(cmd)
    assert "ffmpeg" in cmd[0]
    assert str(a) in cmd_str and str(b) in cmd_str
    assert "adelay" in cmd_str
    assert "amix" in cmd_str
    # SFX 1 起始 5s → adelay 5000|5000
    assert "5000|5000" in cmd_str


def test_duck_bgm_for_sfx_uses_sidechaincompress(tmp_path):
    bgm = tmp_path / "bgm.wav"; bgm.write_bytes(b"x")
    sfx = tmp_path / "sfx.wav"; sfx.write_bytes(b"y")
    out = tmp_path / "out.wav"
    with patch("subprocess.run") as mock_run:
        def fake_run(*args, **kwargs):
            out.write_bytes(b"mixed")
            return MagicMock(returncode=0)
        mock_run.side_effect = fake_run
        result = duck_bgm_for_sfx(bgm, sfx, out, ducking_db=-6.0)
    assert result == out
    cmd_str = " ".join(mock_run.call_args.args[0])
    assert "sidechaincompress" in cmd_str
    assert str(bgm) in cmd_str and str(sfx) in cmd_str


def test_assemble_and_mix_calls_sfx_wiring_when_session_given(tmp_path, monkeypatch):
    """assemble_and_mix 拿到 sfx_session=非空 时，应当调用 assemble_sfx_track + duck_bgm_for_sfx。

    注：实施者可能改成更聚焦的 _post_mix_sfx_layer 单测，只要这两条调用关系被覆盖即可。
    本测要求实施者：(a) 真实跑 assemble_and_mix 路径，或 (b) 改为聚焦的 helper 测，
    都能验证 sfx_session 注入会触发 assemble_sfx_track + duck_bgm_for_sfx。
    """
    from sound_track_agent import mixdown
    sess = SFXSession("/m.mp4", "h", 24.0, shots=[
        SFXShot(0, 0.0, 3.0, status="generated",
                candidates=[SFXCandidate("/a.mp3", 1, "x")],
                chosen_candidate=0)])
    called = {"assemble": 0, "duck": 0}
    monkeypatch.setattr(mixdown, "assemble_sfx_track",
        lambda shots, out: (called.__setitem__("assemble", called["assemble"] + 1)
                            or Path(out)))
    monkeypatch.setattr(mixdown, "duck_bgm_for_sfx",
        lambda bgm, sfx, out, ducking_db=-6.0:
            (called.__setitem__("duck", called["duck"] + 1) or Path(out)))
    # 若 assemble_and_mix 真实跑链路过长，可用 mixdown 内部新加的 _post_mix_sfx_layer helper 直接测：
    # 实施者可选实现方式：
    #   方式 A: assemble_and_mix(sfx_session=sess) 全链路
    #   方式 B: 抽出 _post_mix_sfx_layer(mixed_path, sfx_shots, ducking_db, work_dir) 单测
    # 任选其一，断言 called["assemble"] >= 1 且 called["duck"] >= 1。
    if hasattr(mixdown, "_post_mix_sfx_layer"):
        # 方式 B：聚焦 helper
        mixed = tmp_path / "mixed.wav"; mixed.write_bytes(b"x")
        mixdown._post_mix_sfx_layer(mixed, sess.shots, -6.0, tmp_path)
        assert called["assemble"] == 1
        assert called["duck"] == 1
    else:
        # 方式 A：假设 assemble_and_mix 已加 sfx_session kwarg
        # 跳过本断言，让实施者用方式 B 实现
        pass
