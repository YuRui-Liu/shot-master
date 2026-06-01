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


def has_audio_stream(video_path: str) -> bool:
    """ffprobe 检测视频是否含音轨；探测失败时保守返回 True（避免误删音频）。"""
    cmd = [ffprobe_path(), "-v", "error", "-select_streams", "a",
           "-show_entries", "stream=index", "-of", "csv=p=0", str(video_path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=False)
        return bool((proc.stdout or b"").strip())
    except Exception:
        return True


def probe_video_meta(video_path: str) -> dict:
    """单次 ffprobe 提取视频元信息（时长/宽高/fps/编码/has_audio）。

    返回 dict 含: duration(float秒), width(int), height(int), fps(float),
                     codec(str), has_audio(bool)
    探测失败时返回全默认值（不抛）。
    """
    fallback = {
        "duration": 0.0,
        "width": 0,
        "height": 0,
        "fps": 0.0,
        "codec": "",
        "has_audio": False,
    }
    cmd = [
        ffprobe_path(), "-v", "error",
        "-show_entries",
        "stream=index,codec_type,codec_name,width,height,r_frame_rate:"
        "format=duration",
        "-of", "json", str(video_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=False)
        data = json.loads(proc.stdout or b"{}")
    except Exception:
        return fallback

    # --- duration from format ---
    try:
        duration = float(data.get("format", {}).get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0

    # --- first video stream ---
    width = 0
    height = 0
    fps = 0.0
    codec = ""
    has_audio = False

    streams = data.get("streams") or []
    for s in streams:
        ct = (s.get("codec_type") or "").lower()
        if ct == "video":
            width = int(s.get("width") or 0)
            height = int(s.get("height") or 0)
            codec = s.get("codec_name") or ""
            # r_frame_rate is a string like "30000/1001"
            rfr = s.get("r_frame_rate") or ""
            if rfr and "/" in rfr:
                parts = rfr.split("/")
                try:
                    fps = float(parts[0]) / float(parts[1])
                except (ValueError, ZeroDivisionError):
                    fps = 0.0
            break  # only first video stream
        if ct == "audio":
            has_audio = True

    # re-scan for audio in case audio stream appeared before video
    if not has_audio:
        for s in streams:
            if (s.get("codec_type") or "").lower() == "audio":
                has_audio = True
                break

    return {
        "duration": duration,
        "width": width,
        "height": height,
        "fps": round(fps, 3),
        "codec": codec,
        "has_audio": has_audio,
    }
