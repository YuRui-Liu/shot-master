import numpy as np
import soundfile as sf
import pytest
from sound_track_agent.bgm_assembler import assemble_bgm


def _tone(path, freq, sr=22050, dur=1.0):
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    sf.write(str(path), (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32), sr)


def test_assemble_single_segment(tmp_path):
    a = tmp_path / "a.wav"; _tone(a, 220, dur=1.0)
    out = tmp_path / "full.wav"
    res = assemble_bgm([a], out)
    assert res == out and out.exists()
    y, sr = sf.read(str(out))
    assert abs(len(y) / sr - 1.0) < 0.2


def test_assemble_three_segments_crossfaded(tmp_path):
    paths = []
    for i, f in enumerate((220, 330, 440)):
        p = tmp_path / f"s{i}.wav"; _tone(p, f, dur=1.0); paths.append(p)
    out = tmp_path / "full.wav"
    res = assemble_bgm(paths, out, crossfade=0.3)
    assert res == out and out.exists()
    y, sr = sf.read(str(out))
    assert abs(len(y) / sr - 2.4) < 0.3      # 3 - 2*0.3


def test_assemble_empty_raises(tmp_path):
    with pytest.raises(ValueError):
        assemble_bgm([], tmp_path / "x.wav")
