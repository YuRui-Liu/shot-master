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
from sound_track_agent.audio_mixer import extract_audio, replace_video_audio


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
