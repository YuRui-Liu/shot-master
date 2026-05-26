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
