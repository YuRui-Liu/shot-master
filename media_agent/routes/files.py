"""本地文件流式服务端点 — GET /file?path=...[&project=...]。

本地单用户工具：允许绝对路径直读；相对路径用 project 目录解析。
按扩展名映射 content-type，FileResponse 流式返回（图/视频/音频）。
- path 空 → 400
- 文件不存在或非文件 → 404
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()

# 扩展名 → media_type。未列出的按 application/octet-stream 兜底交给 FileResponse。
_MEDIA_TYPES = {
    # 图
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    # 视频
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    # 音频
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
}


def _resolve(path: str, project: str) -> Path:
    """绝对路径直接用；相对路径以 project 为基。"""
    p = Path(path)
    if p.is_absolute():
        return p
    base = Path(project) if project else Path()
    return base / p


@router.get("/file")
def get_file(path: str, project: str = ""):
    """流式返回本地媒体文件。"""
    raw = (path or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="path 不能为空")

    target = _resolve(raw, (project or "").strip())
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在: {path}")

    media_type = _MEDIA_TYPES.get(target.suffix.lower())
    return FileResponse(str(target), media_type=media_type, filename=target.name)
