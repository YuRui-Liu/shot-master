"""mix 完整链：抽帧 / 取段 BGM 拼接 / 分离对白 / ducking / 写回视频。"""
from __future__ import annotations

import subprocess
from pathlib import Path

from sound_track_agent.session import ScoringSession, SegmentScore
from sound_track_agent.bgm_assembler import assemble_bgm
from sound_track_agent.audio_mixer import (
    separate_vocals, duck_and_mix, extract_audio, replace_video_audio,
    assemble_dialogue_track,
)
from sound_track_agent.accent_mixer import apply_pump, clip_targets
from sound_track_agent.beat_aligner import align_beats_to_accents
from sound_track_agent.shot_detector import _video_duration_seconds


def extract_segment_frame(video_path, seg: SegmentScore, out_png, *,
                          runner=subprocess.run) -> Path:
    """抽 segment 中点帧为 png（供情绪分析）。"""
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    mid = (seg.t_start + seg.t_end) / 2.0
    cmd = ["ffmpeg", "-y", "-ss", f"{mid:.3f}", "-i", str(video_path),
           "-frames:v", "1", str(out_png)]
    result = runner(cmd, capture_output=True)
    if getattr(result, "returncode", 0) != 0 or not out_png.exists():
        raise RuntimeError(f"ffmpeg 抽帧失败 @ {mid:.3f}s")
    return out_png


def _chosen_bgm(seg: SegmentScore) -> str:
    if not seg.candidates:
        raise RuntimeError(f"段 {seg.index} 无 BGM 候选")
    idx = seg.chosen_candidate if seg.chosen_candidate is not None else 0
    return seg.candidates[idx].path


def assemble_and_mix(sess: ScoringSession, video_path, work_dir, *,
                     crossfade: float = 0.5,
                     target_lufs: float = -14.0,
                     big_threshold: float = 0.7,
                     snap_window: float = 0.6,
                     max_stretch: float = 0.10,
                     separate=separate_vocals,
                     assemble_dialogue=None,
                     align_beats=None,
                     apply_pump_fn=None,
                     assemble_bgm_fn=None,
                     extract_audio_fn=None,
                     duck_and_mix_fn=None,
                     replace_video_audio_fn=None,
                     duration_of=None,
                     sfx_session=None,
                     sfx_ducking_db: float = -6.0) -> str:
    """段 BGM 拼接 → 卡点对齐+泵感（跳过对齐爆点） → 装对白轨(或 Demucs) →
    ducking → 写回视频。所有 I/O 可注入（测试用）。"""
    # 默认值引用模块级名称，使 monkeypatch 仍然生效
    _assemble_dialogue = assemble_dialogue or assemble_dialogue_track
    _align_beats = align_beats or align_beats_to_accents
    _apply_pump = apply_pump_fn or apply_pump
    _assemble_bgm = assemble_bgm_fn or assemble_bgm
    _extract_audio = extract_audio_fn or extract_audio
    _duck_and_mix = duck_and_mix_fn or duck_and_mix
    _replace_video_audio = replace_video_audio_fn or replace_video_audio
    if duration_of is None:
        def _safe_duration(v):
            try:
                return _video_duration_seconds(v)
            except Exception:
                return 0.0
        _duration_of = _safe_duration
    else:
        _duration_of = duration_of

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    seg_bgms = [_chosen_bgm(s) for s in sess.segments]
    accents = list(getattr(sess, "accent_points", []) or [])
    use_accent = bool(getattr(sess, "accent_mix_enabled", True)) and bool(accents)
    gains = [float(getattr(s, "volume", 1.0)) for s in sess.segments]

    if use_accent:
        targets = clip_targets([s.duration for s in sess.segments], accents,
                               big_threshold=big_threshold, window=snap_window,
                               min_clip=crossfade)
        raw_bgm = _assemble_bgm(seg_bgms, work_dir / "full_bgm.wav",
                                crossfade=crossfade, clip_durations=targets,
                                clip_gains=gains)
        stretched, aligned = _align_beats(
            raw_bgm, accents, max_stretch=max_stretch,
            big_threshold=big_threshold,
            out_path=work_dir / "full_bgm_aligned.wav")
        full_bgm = _apply_pump(stretched, work_dir / "full_bgm_pumped.wav",
                               accents,
                               strength=float(getattr(sess, "pump_strength", 0.6)),
                               skip_indices=aligned)
    else:
        full_bgm = _assemble_bgm(seg_bgms, work_dir / "full_bgm.wav",
                                 crossfade=crossfade, clip_gains=gains)

    if sess.dialogue_segments:
        total_dur = float(_duration_of(video_path))
        vocals = _assemble_dialogue(
            sess.dialogue_segments, total_dur,
            work_dir / "dialogue_track.wav")
    else:
        src_audio = _extract_audio(video_path, work_dir / "src_audio.wav")
        vocals, _rest = separate(src_audio, work_dir / "sep")

    mixed = _duck_and_mix(vocals, full_bgm, work_dir / "mixed.wav",
                          target_lufs=target_lufs)

    # Phase 4a: SFX 层接入
    if sfx_session is not None:
        mixed = _post_mix_sfx_layer(
            mixed, sfx_session.shots,
            float(sfx_ducking_db), work_dir)

    out_video = work_dir / (Path(video_path).stem + "_scored.mp4")
    _replace_video_audio(video_path, mixed, out_video)
    return str(out_video)


# ---------------------------------------------------------------------------
# Phase 4a SFX 层：assemble_sfx_track + sidechain ducking
# ---------------------------------------------------------------------------


def assemble_sfx_track(sfx_shots, out_path):
    """收集 enabled+chosen 的 SFX，按 t_start adelay 后 amix。

    空（无可用 SFX）→ 返回 None，调用方应跳过 SFX 混音步骤。
    """
    cues = [(s.t_start, s.candidates[s.chosen_candidate].path, float(s.volume))
            for s in sfx_shots
            if s.enabled and s.chosen_candidate is not None
            and 0 <= s.chosen_candidate < len(s.candidates)
            and s.candidates[s.chosen_candidate].path]
    if not cues:
        return None
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y"]
    for _t, p, _v in cues:
        cmd += ["-i", str(p)]
    parts = []
    inputs_labels = []
    for i, (t, _p, vol) in enumerate(cues):
        delay_ms = max(0, int(round(t * 1000)))
        parts.append(
            f"[{i}:a]adelay={delay_ms}|{delay_ms},volume={vol:.3f}[s{i}]")
        inputs_labels.append(f"[s{i}]")
    mix = "".join(inputs_labels) + f"amix=inputs={len(cues)}:duration=longest:normalize=0[mix]"
    filter_complex = ";".join(parts + [mix])
    cmd += ["-filter_complex", filter_complex,
            "-map", "[mix]", "-c:a", "pcm_s16le", str(out_path)]
    subprocess.run(cmd, check=False, capture_output=True)
    return out_path if out_path.exists() else None


def duck_bgm_for_sfx(bgm_path, sfx_path, out_path, *, ducking_db: float = -6.0):
    """SFX 触发，BGM 被压缩 ducking_db。"""
    out_path = Path(out_path)
    makeup = max(0.0, -float(ducking_db))
    cmd = [
        "ffmpeg", "-y",
        "-i", str(bgm_path),
        "-i", str(sfx_path),
        "-filter_complex",
        f"[0:a][1:a]sidechaincompress=threshold=0.05:ratio=4:"
        f"attack=20:release=200:makeup={makeup}[duck];"
        f"[duck][1:a]amix=inputs=2:duration=first:normalize=0[mix]",
        "-map", "[mix]", "-c:a", "pcm_s16le", str(out_path),
    ]
    subprocess.run(cmd, check=False, capture_output=True)
    return out_path


def _post_mix_sfx_layer(mixed_path, sfx_shots, ducking_db: float, work_dir):
    """mix 完成后追加 SFX 层 + ducking。返回最终 mixed path（可能就是输入路径，如果无 SFX）。"""
    sfx_track = assemble_sfx_track(sfx_shots, Path(work_dir) / "sfx_track.wav")
    if sfx_track is None:
        return mixed_path
    return duck_bgm_for_sfx(
        Path(mixed_path), sfx_track,
        Path(work_dir) / "mixed_with_sfx.wav",
        ducking_db=ducking_db)


def extract_frames_at(video_path, times: list[float], out_dir, *,
                      runner=subprocess.run) -> list[Path]:
    """对每个时间点 ffmpeg -ss t -frames:v 1 抽帧。

    返回 list[Path] 与 times 一一对应。任一帧抽帧失败抛 RuntimeError。
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i, t in enumerate(times):
        p = out_dir / f"f{i}_{float(t):.3f}.png"
        cmd = ["ffmpeg", "-y", "-ss", f"{float(t):.3f}", "-i", str(video_path),
               "-frames:v", "1", str(p)]
        result = runner(cmd, capture_output=True)
        if getattr(result, "returncode", 0) != 0 or not p.exists():
            raise RuntimeError(f"ffmpeg 抽帧失败 @ {float(t):.3f}s")
        paths.append(p)
    return paths
