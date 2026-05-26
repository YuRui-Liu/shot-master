"""分段 BGM → crossfade 拼接成整条（ffmpeg acrossfade 链式）。"""
from __future__ import annotations

import subprocess
from pathlib import Path


def assemble_bgm(bgm_paths: list, out_path, *,
                 crossfade: float = 0.5,
                 runner=subprocess.run) -> Path:
    """把分段 BGM 按顺序 crossfade 拼成整条。

    1 段：直接转码到 out。≥2 段：链式 acrossfade（每对重叠 crossfade 秒）。
    """
    if not bgm_paths:
        raise ValueError("assemble_bgm 需要至少 1 段 BGM")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    paths = [str(p) for p in bgm_paths]

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
