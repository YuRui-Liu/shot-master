import sys
from pathlib import Path
import pytest

from sound_track_agent.audio_mixer import separate_vocals


def test_separate_vocals_builds_demucs_cmd_and_parses_paths(tmp_path):
    audio = tmp_path / "ep1.wav"
    audio.write_bytes(b"RIFF....")
    out = tmp_path / "sep"
    calls = []

    def fake_runner(cmd, **kw):
        calls.append(cmd)
        d = out / "htdemucs" / "ep1"
        d.mkdir(parents=True, exist_ok=True)
        (d / "vocals.wav").write_bytes(b"v")
        (d / "no_vocals.wav").write_bytes(b"n")
        class _R: returncode = 0
        return _R()

    vocals, rest = separate_vocals(audio, out, runner=fake_runner)
    assert vocals.name == "vocals.wav" and vocals.exists()
    assert rest.name == "no_vocals.wav" and rest.exists()
    cmd = calls[0]
    assert sys.executable in cmd or "python" in cmd[0]
    assert "demucs" in cmd
    assert "--two-stems" in cmd and "vocals" in cmd
    assert "-o" in cmd
    assert str(audio) in cmd


def test_separate_vocals_raises_when_output_missing(tmp_path):
    audio = tmp_path / "ep.wav"; audio.write_bytes(b"x")
    def fake_runner(cmd, **kw):
        class _R: returncode = 0
        return _R()
    with pytest.raises(FileNotFoundError):
        separate_vocals(audio, tmp_path / "o", runner=fake_runner)


import numpy as np
import soundfile as sf
from sound_track_agent.audio_mixer import duck_and_mix


def _tone(path, freq, sr=22050, dur=1.0):
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    sf.write(str(path), (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32), sr)


def test_duck_and_mix_produces_audio(tmp_path):
    voc = tmp_path / "voc.wav"; _tone(voc, 220)
    bgm = tmp_path / "bgm.wav"; _tone(bgm, 440)
    out = tmp_path / "mixed.wav"
    res = duck_and_mix(voc, bgm, out)
    assert res == out and out.exists()
    y, sr = sf.read(str(out))
    assert len(y) > 0
    assert sr > 0


import subprocess as _sp
from sound_track_agent.audio_mixer import extract_audio, replace_video_audio, assemble_dialogue_track
from sound_track_agent.session import DialogueSegment


class _FakeResult:
    def __init__(self, returncode=0):
        self.returncode = returncode
        self.stderr = b""


def test_assemble_dialogue_track_empty_uses_silence_only(tmp_path):
    """空段列表 → 只生成静音底轨。"""
    captured = {}
    def runner(cmd, capture_output=False):
        captured["cmd"] = cmd
        (tmp_path / "out.wav").write_bytes(b"WAV")
        return _FakeResult(returncode=0)
    out = assemble_dialogue_track(
        [], total_duration=5.0, out_path=tmp_path / "out.wav", runner=runner)
    cmd = captured["cmd"]
    assert "anullsrc=channel_layout=stereo:sample_rate=44100" in " ".join(cmd)
    assert "-filter_complex" not in cmd                # 单输入路径
    assert out == tmp_path / "out.wav"


def test_assemble_dialogue_track_segments_adelay_and_amix(tmp_path):
    captured = {}
    def runner(cmd, capture_output=False):
        captured["cmd"] = cmd
        (tmp_path / "out.wav").write_bytes(b"WAV")
        return _FakeResult(returncode=0)
    segs = [DialogueSegment(audio_path="/x/a.flac", t_start=0.0, duration=1.0),
            DialogueSegment(audio_path="/x/b.flac", t_start=1.5, duration=0.8),
            DialogueSegment(audio_path="/x/c.flac", t_start=3.0, duration=0.5)]
    assemble_dialogue_track(segs, total_duration=5.0,
                            out_path=tmp_path / "out.wav", runner=runner)
    cmd = " ".join(captured["cmd"])
    assert "-i /x/a.flac" in cmd
    assert "-i /x/b.flac" in cmd
    assert "-i /x/c.flac" in cmd
    assert "adelay=0:all=1" in cmd                     # 边界：t=0
    assert "adelay=1500:all=1" in cmd                  # 1.5s → 1500ms
    assert "adelay=3000:all=1" in cmd
    assert "amix=inputs=4:duration=first:normalize=0" in cmd


def test_assemble_dialogue_track_ffmpeg_failure_raises(tmp_path):
    def runner(cmd, capture_output=False):
        return _FakeResult(returncode=1)
    with pytest.raises(RuntimeError, match="ffmpeg"):
        assemble_dialogue_track([], total_duration=2.0,
                                out_path=tmp_path / "out.wav", runner=runner)


def _make_video_with_audio(path, sr=22050, dur=1.0, fps=24):
    """造一个带音轨的小 mp4（纯色视频 + 正弦音）。"""
    import cv2
    apath = str(path) + ".a.wav"
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    sf.write(apath, (0.3 * np.sin(2 * np.pi * 330 * t)).astype(np.float32), sr)
    vtmp = str(path) + ".v.mp4"
    vw = cv2.VideoWriter(vtmp, cv2.VideoWriter_fourcc(*"mp4v"), float(fps), (64, 64))
    for _ in range(int(fps * dur)):
        vw.write(np.full((64, 64, 3), 128, np.uint8))
    vw.release()
    _sp.run(["ffmpeg", "-y", "-i", vtmp, "-i", apath,
             "-c:v", "copy", "-c:a", "aac", "-shortest", str(path)],
            capture_output=True, check=True)


def test_extract_audio(tmp_path):
    v = tmp_path / "clip.mp4"; _make_video_with_audio(v)
    out = tmp_path / "a.wav"
    res = extract_audio(v, out)
    assert res == out and out.exists()
    y, sr = sf.read(str(out))
    assert len(y) > 0


def test_replace_video_audio(tmp_path):
    v = tmp_path / "clip.mp4"; _make_video_with_audio(v)
    newa = tmp_path / "new.wav"
    t = np.linspace(0, 1.0, 22050, endpoint=False)
    sf.write(str(newa), (0.2 * np.sin(2 * np.pi * 660 * t)).astype(np.float32), 22050)
    out = tmp_path / "out.mp4"
    res = replace_video_audio(v, newa, out)
    assert res == out and out.exists()
    assert out.stat().st_size > 0
