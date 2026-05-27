"""mix 完整链：抽帧 / 取段 BGM 拼接 / 分离对白 / ducking / 写回视频。"""
from __future__ import annotations

import subprocess
from pathlib import Path

from sound_track_agent.session import ScoringSession, SegmentScore
from sound_track_agent.bgm_assembler import assemble_bgm
from sound_track_agent.audio_mixer import (
    separate_vocals, duck_and_mix, extract_audio, replace_video_audio)
from sound_track_agent.accent_mixer import apply_pump, clip_targets


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
                     separate=separate_vocals,
                     target_lufs: float = -14.0,
                     big_threshold: float = 0.7,
                     snap_window: float = 0.6) -> str:
    """段 BGM 拼接 →(可选)段切对齐+泵感 → 分离对白 → ducking → 写回视频。

    当 sess.accent_mix_enabled 且有卡点时启用卡点路径;否则等同原逻辑(零回归)。
    """
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    seg_bgms = [_chosen_bgm(s) for s in sess.segments]
    accents = list(getattr(sess, "accent_points", []) or [])
    use_accent = bool(getattr(sess, "accent_mix_enabled", True)) and bool(accents)

    if use_accent:
        targets = clip_targets([s.duration for s in sess.segments], accents,
                               big_threshold=big_threshold, window=snap_window)
        full_bgm = assemble_bgm(seg_bgms, work_dir / "full_bgm.wav",
                                crossfade=crossfade, clip_durations=targets)
        full_bgm = apply_pump(full_bgm, work_dir / "full_bgm_pumped.wav",
                              accents,
                              strength=float(getattr(sess, "pump_strength", 0.6)))
    else:
        full_bgm = assemble_bgm(seg_bgms, work_dir / "full_bgm.wav",
                                crossfade=crossfade)

    src_audio = extract_audio(video_path, work_dir / "src_audio.wav")
    vocals, _rest = separate(src_audio, work_dir / "sep")

    mixed = duck_and_mix(vocals, full_bgm, work_dir / "mixed.wav",
                         target_lufs=target_lufs)

    out_video = work_dir / (Path(video_path).stem + "_scored.mp4")
    replace_video_audio(video_path, mixed, out_video)
    return str(out_video)
