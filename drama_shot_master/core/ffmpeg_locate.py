"""定位 ffmpeg/ffprobe：优先随包目录，回退系统 PATH，缺失抛错（不静默）。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _bundled_dir() -> Path:
    """随包二进制目录：PyInstaller(_MEIPASS)/Nuitka/源码态均落到 assets/bin。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "assets" / "bin"
    return Path(__file__).resolve().parent.parent / "assets" / "bin"


def _exe(name: str) -> str:
    return f"{name}.exe" if os.name == "nt" else name


def _resolve(name: str) -> str:
    cand = _bundled_dir() / _exe(name)
    if cand.exists():
        return str(cand)
    found = shutil.which(name)
    if found:
        return found
    raise FileNotFoundError(
        f"未找到 {name}。请确认随包 assets/bin/{_exe(name)} 存在，或系统 PATH 中已安装 ffmpeg。")


def ffmpeg_path() -> str:
    return _resolve("ffmpeg")


def ffprobe_path() -> str:
    return _resolve("ffprobe")


def probe_duration(video_path: str) -> float:
    """ffprobe 取时长（秒）；失败返回 0.0（不抛，交由上层校验）。"""
    cmd = [ffprobe_path(), "-v", "error", "-show_entries", "format=duration",
           "-of", "json", str(video_path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=False)
        data = json.loads(proc.stdout or b"{}")
        return float(data.get("format", {}).get("duration") or 0.0)
    except Exception:
        return 0.0
