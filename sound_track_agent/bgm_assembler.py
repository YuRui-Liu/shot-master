"""分段 BGM → crossfade 拼接成整条（ffmpeg acrossfade 链式）。"""
from __future__ import annotations

import subprocess
from pathlib import Path


def assemble_bgm(bgm_paths: list, out_path, *,
                 crossfade: float = 0.5,
                 clip_durations: list | None = None,
                 clip_gains: list | None = None,
                 runner=subprocess.run) -> Path:
    """把分段 BGM 按顺序 crossfade 拼成整条。

    clip_durations / clip_gains(可选,长度需 == bgm_paths):分别把对应 clip 先裁到
    目标秒数(trim-only)、按线性倍数调音量(ffmpeg volume=)。二者可同时给;某段都不需要
    则用原片。处理失败降级用原片。
    """
    if not bgm_paths:
        raise ValueError("assemble_bgm 需要至少 1 段 BGM")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    paths = [str(p) for p in bgm_paths]
    if clip_durations is not None and len(clip_durations) != len(paths):
        raise ValueError("clip_durations 长度需与 bgm_paths 一致")
    if clip_gains is not None and len(clip_gains) != len(paths):
        raise ValueError("clip_gains 长度需与 bgm_paths 一致")

    if clip_durations is not None or clip_gains is not None:
        resolved = []
        for i, p in enumerate(paths):
            dur = clip_durations[i] if clip_durations is not None else None
            gain = clip_gains[i] if clip_gains is not None else None
            need_trim = dur is not None
            need_gain = gain is not None and abs(float(gain) - 1.0) > 1e-6
            if not need_trim and not need_gain:
                resolved.append(p)
                continue
            tp = str(out_path.parent / f"_proc{i}.wav")
            cmd = ["ffmpeg", "-y", "-i", p]
            if need_trim:
                cmd += ["-t", f"{float(dur):.3f}"]
            if need_gain:
                cmd += ["-af", f"volume={float(gain):.4f}"]
            cmd += ["-c:a", "pcm_s16le", tp]
            r = runner(cmd, capture_output=True)
            resolved.append(tp if getattr(r, "returncode", 0) == 0
                            and Path(tp).exists() else p)
        paths = resolved

    cmd = ["ffmpeg", "-y"]
    for p in paths:
        cmd += ["-i", p]

    if len(paths) == 1:
        cmd += ["-c:a", "pcm_s16le", str(out_path)]
    else:
        parts = []
        prev = "[0]"
        for i in range(1, len(paths)):
            label = f"[a{i}]" if i < len(paths) - 1 else "[out]"
            parts.append(
                f"{prev}[{i}]acrossfade=d={crossfade}:c1=tri:c2=tri{label}")
            prev = label
        filter_complex = ";".join(parts)
        cmd += ["-filter_complex", filter_complex, "-map", "[out]",
                str(out_path)]

    result = runner(cmd, capture_output=True)
    if getattr(result, "returncode", 0) != 0:
        err = getattr(result, "stderr", b"")
        msg = err.decode("utf-8", "ignore")[-400:] if isinstance(err, bytes) else str(err)[-400:]
        raise RuntimeError(f"ffmpeg acrossfade 拼接失败: {msg}")
    if not out_path.exists():
        raise FileNotFoundError(f"ffmpeg 未产出 {out_path}")
    return out_path
