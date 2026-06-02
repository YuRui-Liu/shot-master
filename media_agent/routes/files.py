"""本地文件流式服务端点 — GET /file?path=...[&project=...]。

本地单用户工具：允许绝对路径直读；相对路径用 project 目录解析。
按扩展名映射 content-type，FileResponse 流式返回（图/视频/音频）。
视频文件支持 HTTP Range 请求（206 Partial Content），浏览器 seek/缓冲必需。
- path 空 → 400
- 文件不存在或非文件 → 404
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

router = APIRouter()


def _is_cover_request(path_str: str) -> bool:
    """检查请求路径是否指向项目的 cover.jpg / cover.png 等封面文件。"""
    name = Path(path_str).name.lower()
    return name in ("cover.jpg", "cover.jpeg", "cover.png", "cover.webp")


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
# 需要 Range 支持的媒体类型（视频 + 音频，浏览器 seek/缓冲必需 HTTP 206）
_VIDEO_AUDIO_EXTS = frozenset({
    ".mp4", ".mov", ".webm", ".mkv", ".wav", ".mp3", ".m4a", ".ogg", ".flac",
})


def _resolve(path: str, project: str) -> Path:
    """绝对路径直接用；相对路径以 project 为基。"""
    p = Path(path)
    if p.is_absolute():
        return p
    base = Path(project) if project else Path()
    return base / p


def _range_response(target: Path, media_type: str, request: Request) -> Response:
    """为视频/音频文件提供 HTTP Range 支持（206 Partial Content）。

    浏览器播放视频需要 Range 请求来 seek/缓冲；Starlette FileResponse 不支持 Range，
    故手动解析 Range 头并返回部分内容。"""
    file_size = target.stat().st_size
    range_header = request.headers.get("range", "").strip()

    if not range_header.startswith("bytes="):
        # 无 Range → 全文件（挂 Accept-Ranges 允许浏览器后续发 Range）
        resp = FileResponse(str(target), media_type=media_type, filename=target.name)
        resp.headers["Accept-Ranges"] = "bytes"
        return resp

    # 解析 Range: bytes=0-1048575
    range_bytes = range_header[6:]
    start_str, _, end_str = range_bytes.partition("-")
    try:
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else (file_size - 1)
    except ValueError:
        return FileResponse(str(target), media_type=media_type, filename=target.name,
                            status_code=200, headers={"Accept-Ranges": "bytes"})

    # 边界修正
    start = max(0, start)
    end = min(file_size - 1, end)
    if start > end:
        start = 0  # 无效 range → 回退全文件

    content_length = end - start + 1

    def _read_range():
        with open(target, "rb") as fh:
            fh.seek(start)
            yield fh.read(content_length)

    return StreamingResponse(
        _read_range(),
        status_code=206,
        media_type=media_type,
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(content_length),
        })


@router.get("/file")
def get_file(path: str, project: str = "", request: Request = None):
    """流式返回本地媒体文件。视频/音频支持 HTTP Range (206)。"""
    raw = (path or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="path 不能为空")

    target = _resolve(raw, (project or "").strip())
    if not target.exists() or not target.is_file():
        if _is_cover_request(raw):
            return Response(status_code=204)
        raise HTTPException(status_code=404, detail=f"文件不存在: {path}")

    ext = target.suffix.lower()
    media_type = _MEDIA_TYPES.get(ext)

    # 视频/音频：走 Range 支持路径（浏览器播放必需 206 Partial Content）
    if ext in _VIDEO_AUDIO_EXTS and request is not None:
        return _range_response(target, media_type, request)

    return FileResponse(str(target), media_type=media_type, filename=target.name)
