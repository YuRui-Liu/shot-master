"""成片音频处理：Demucs 分离对白 + FFmpeg ducking 混音。

Demucs 4.0.1 无 python api，走 CLI；FFmpeg 走子进程。所有外部命令经可注入的
runner，便于单测 mock（真跑 Demucs 需下载 ~300MB 权重）。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

DEMUCS_MODEL = "htdemucs"      # Demucs 默认模型，输出子目录名


def separate_vocals(audio_path, out_dir, *,
                    runner=subprocess.run) -> tuple[Path, Path]:
    """用 Demucs CLI 把音频分成 vocals(对白) / no_vocals(其余)。

    返回 (vocals_path, no_vocals_path)。命令失败或产物缺失抛错。
    """
    audio_path = Path(audio_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "demucs", "--two-stems", "vocals",
           "-o", str(out_dir), str(audio_path)]
    result = runner(cmd)
    if getattr(result, "returncode", 0) != 0:
        raise RuntimeError(f"demucs 分离失败 (returncode={result.returncode})")
    stem = audio_path.stem
    base = out_dir / DEMUCS_MODEL / stem
    vocals = base / "vocals.wav"
    no_vocals = base / "no_vocals.wav"
    if not vocals.exists() or not no_vocals.exists():
        raise FileNotFoundError(
            f"demucs 未在 {base} 产出 vocals/no_vocals.wav")
    return vocals, no_vocals


def duck_and_mix(vocals_path, bgm_path, out_path, *,
                 target_lufs: float = -14.0,
                 runner=subprocess.run) -> Path:
    """BGM 以 vocals 为 sidechain 自动 ducking，与 vocals 混合并响度归一化。

    [1=bgm] 被 [0=vocals] 压低 → 与 vocals amix → loudnorm。输出 out_path。
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    filter_complex = (
        "[1:a][0:a]sidechaincompress="
        "threshold=0.03:ratio=8:attack=20:release=300[bgmducked];"
        "[0:a][bgmducked]amix=inputs=2:duration=longest:dropout_transition=0[mix];"
        f"[mix]loudnorm=I={target_lufs}:TP=-1:LRA=11[out]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(vocals_path),
        "-i", str(bgm_path),
        "-filter_complex", filter_complex,
        "-map", "[out]",
        str(out_path),
    ]
    result = runner(cmd, capture_output=True)
    if getattr(result, "returncode", 0) != 0:
        err = getattr(result, "stderr", b"")
        msg = err.decode("utf-8", "ignore")[-400:] if isinstance(err, bytes) else str(err)[-400:]
        raise RuntimeError(f"ffmpeg ducking 混音失败: {msg}")
    if not out_path.exists():
        raise FileNotFoundError(f"ffmpeg 未产出 {out_path}")
    return out_path
