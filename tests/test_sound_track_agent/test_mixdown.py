import numpy as np, soundfile as sf, subprocess
from pathlib import Path
from sound_track_agent.mixdown import assemble_and_mix, extract_segment_frame
from sound_track_agent.session import ScoringSession, SegmentScore, BGMCandidate


def _make_video_with_audio(path, dur=2.0, sr=22050, fps=24):
    import cv2
    apath = str(path) + ".a.wav"
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    sf.write(apath, (0.3 * np.sin(2 * np.pi * 330 * t)).astype(np.float32), sr)
    vtmp = str(path) + ".v.mp4"
    vw = cv2.VideoWriter(vtmp, cv2.VideoWriter_fourcc(*"mp4v"), float(fps), (64, 64))
    for _ in range(int(fps * dur)):
        vw.write(np.full((64, 64, 3), 128, np.uint8))
    vw.release()
    subprocess.run(["ffmpeg", "-y", "-i", vtmp, "-i", apath, "-c:v", "copy",
                    "-c:a", "aac", "-shortest", str(path)], capture_output=True, check=True)


def _tone(path, freq, sr=22050, dur=1.0):
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    sf.write(str(path), (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32), sr)


def test_extract_segment_frame(tmp_path):
    v = tmp_path / "clip.mp4"; _make_video_with_audio(v)
    out = tmp_path / "f.png"
    seg = SegmentScore(index=0, t_start=0.0, t_end=2.0)
    res = extract_segment_frame(v, seg, out)
    assert res == out and out.exists() and out.stat().st_size > 0


def test_assemble_and_mix_end_to_end(tmp_path):
    v = tmp_path / "clip.mp4"; _make_video_with_audio(v, dur=2.0)
    b0 = tmp_path / "b0.wav"; _tone(b0, 440, dur=1.0)
    b1 = tmp_path / "b1.wav"; _tone(b1, 550, dur=1.0)
    sess = ScoringSession(
        source_mp4=str(v), source_hash="h", global_style="x", frame_rate=24.0,
        segments=[
            SegmentScore(index=0, t_start=0.0, t_end=1.0,
                         candidates=[BGMCandidate(path=str(b0), seed=1, prompt="t")],
                         chosen_candidate=0),
            SegmentScore(index=1, t_start=1.0, t_end=2.0,
                         candidates=[BGMCandidate(path=str(b1), seed=1, prompt="t")],
                         chosen_candidate=0),
        ])

    def fake_separate(audio_path, out_dir, **kw):
        return Path(audio_path), Path(audio_path)   # 原音轨当 vocals（避免真跑 demucs）

    out = assemble_and_mix(sess, v, tmp_path / "work", separate=fake_separate)
    assert Path(out).exists()
    assert Path(out).stat().st_size > 0


from sound_track_agent.session import AccentPoint


def _two_seg_sess(v, b0, b1, *, enabled, accents):
    s = ScoringSession(
        source_mp4=str(v), source_hash="h", global_style="x", frame_rate=24.0,
        segments=[
            SegmentScore(index=0, t_start=0.0, t_end=1.0,
                         candidates=[BGMCandidate(path=str(b0), seed=1, prompt="t")],
                         chosen_candidate=0),
            SegmentScore(index=1, t_start=1.0, t_end=2.0,
                         candidates=[BGMCandidate(path=str(b1), seed=1, prompt="t")],
                         chosen_candidate=0)])
    s.accent_mix_enabled = enabled
    s.accent_points = list(accents)
    return s


def _fake_separate(audio_path, out_dir, **kw):
    return Path(audio_path), Path(audio_path)


def test_accent_path_calls_pump_when_enabled(tmp_path, monkeypatch):
    import sound_track_agent.mixdown as m
    v = tmp_path / "clip.mp4"; _make_video_with_audio(v, dur=2.0)
    b0 = tmp_path / "b0.wav"; _tone(b0, 440, dur=1.0)
    b1 = tmp_path / "b1.wav"; _tone(b1, 550, dur=1.0)
    seen = {}

    def fake_pump(inp, outp, accents, **kw):
        seen["n"] = len(accents)
        import shutil; shutil.copy(str(inp), str(outp))
        return Path(outp)

    monkeypatch.setattr(m, "apply_pump", fake_pump)
    sess = _two_seg_sess(v, b0, b1, enabled=True,
                         accents=[AccentPoint(t=0.5, intensity=0.9)])
    out = m.assemble_and_mix(sess, v, tmp_path / "w", separate=_fake_separate)
    assert seen.get("n") == 1 and Path(out).exists()


def test_disabled_bypasses_pump(tmp_path, monkeypatch):
    import sound_track_agent.mixdown as m
    v = tmp_path / "clip.mp4"; _make_video_with_audio(v, dur=2.0)
    b0 = tmp_path / "b0.wav"; _tone(b0, 440, dur=1.0)
    b1 = tmp_path / "b1.wav"; _tone(b1, 550, dur=1.0)

    def boom(*a, **k):
        raise AssertionError("关闭时不应调用 apply_pump")

    monkeypatch.setattr(m, "apply_pump", boom)
    sess = _two_seg_sess(v, b0, b1, enabled=False,
                         accents=[AccentPoint(t=0.5, intensity=0.9)])
    out = m.assemble_and_mix(sess, v, tmp_path / "w2", separate=_fake_separate)
    assert Path(out).exists()


def test_assemble_and_mix_passes_clip_gains(tmp_path, monkeypatch):
    import sound_track_agent.mixdown as m
    from sound_track_agent.session import (
        ScoringSession, SegmentScore, BGMCandidate)
    v = tmp_path / "clip.mp4"; _make_video_with_audio(v, dur=2.0)
    b0 = tmp_path / "b0.wav"; _tone(b0, 440, dur=2.0)
    seen = {}
    real_assemble = m.assemble_bgm
    def spy(paths, out, **kw):
        seen["gains"] = kw.get("clip_gains")
        return real_assemble(paths, out, **kw)
    monkeypatch.setattr(m, "assemble_bgm", spy)
    sess = ScoringSession(
        source_mp4=str(v), source_hash="h", global_style="x", frame_rate=24.0,
        segments=[SegmentScore(index=0, t_start=0.0, t_end=2.0,
                  candidates=[BGMCandidate(path=str(b0), seed=1, prompt="t")],
                  chosen_candidate=0)])
    sess.segments[0].volume = 0.5
    sess.accent_mix_enabled = False        # else 分支也要带 gains
    def _sep(a, o, **k):
        from pathlib import Path
        return Path(a), Path(a)
    out = m.assemble_and_mix(sess, v, tmp_path / "w", separate=_sep)
    from pathlib import Path
    assert Path(out).exists()
    assert seen.get("gains") == [0.5]
