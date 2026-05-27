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


def test_assemble_bgm_clip_durations_trims_first_clip(tmp_path):
    b0 = tmp_path / "b0.wav"; _tone(b0, 440, dur=1.0)
    b1 = tmp_path / "b1.wav"; _tone(b1, 550, dur=1.0)
    out = tmp_path / "full.wav"
    assemble_bgm([b0, b1], out, crossfade=0.1, clip_durations=[0.4, None])
    info = sf.info(str(out))
    assert 1.1 < info.duration < 1.5      # 0.4 + 1.0 - 0.1 ≈ 1.3


def test_assemble_bgm_clip_durations_length_mismatch_raises(tmp_path):
    b0 = tmp_path / "b0.wav"; _tone(b0, 440)
    with pytest.raises(ValueError):
        assemble_bgm([b0], tmp_path / "o.wav", clip_durations=[0.4, None])


def test_assemble_bgm_clip_gains_attenuates(tmp_path):
    import numpy as np, soundfile as sf
    from sound_track_agent.bgm_assembler import assemble_bgm

    def _tone(p, f, dur=1.0, sr=22050):
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        sf.write(str(p), (0.5 * np.sin(2 * np.pi * f * t)).astype(np.float32), sr)

    b0 = tmp_path / "b0.wav"; _tone(b0, 440)
    out_loud = tmp_path / "loud.wav"; out_quiet = tmp_path / "quiet.wav"
    assemble_bgm([b0], out_loud, crossfade=0.1)                       # 原音量
    assemble_bgm([b0], out_quiet, crossfade=0.1, clip_gains=[0.25])   # 1/4 音量
    a, _ = sf.read(str(out_loud)); b, _ = sf.read(str(out_quiet))
    assert float(np.abs(b).max()) < float(np.abs(a).max()) * 0.5      # 明显更小


def test_assemble_bgm_clip_gains_length_mismatch_raises(tmp_path):
    import numpy as np, soundfile as sf
    from sound_track_agent.bgm_assembler import assemble_bgm
    import pytest
    b0 = tmp_path / "b0.wav"
    t = np.linspace(0, 1.0, 22050, endpoint=False)
    sf.write(str(b0), (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32), 22050)
    with pytest.raises(ValueError):
        assemble_bgm([b0], tmp_path / "o.wav", clip_gains=[1.0, 0.5])
