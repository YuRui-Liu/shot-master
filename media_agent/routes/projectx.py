"""最近列表维护 + 项目概览聚合端点。纯逻辑、无 Qt。

- /recent/*：删除单条 / 连带删目录 / 清空，走 RecentProjectsManager。
- /project/overview：读项目 manifest（compass.manifest.load_manifest）+ 目录统计，
  聚合成 overview.html 消费的 {project, stages[], next_action, bible, genre} 结构。
"""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from drama_shot_master.core.compass.manifest import load_manifest
from drama_shot_master.core.recent_projects import RecentProjectsManager

router = APIRouter()

# 与 routes/projects.py 一致：仓库根散文件 settings.json，recent_projects.json 同目录
_SETTINGS_PATH = Path("settings.json")


def _manager() -> RecentProjectsManager:
    return RecentProjectsManager.alongside_settings(_SETTINGS_PATH)


# ---------- /recent/* ----------

class PathBody(BaseModel):
    path: str


@router.post("/recent/remove")
def recent_remove(body: PathBody):
    """从最近列表移除一条（不动磁盘）。"""
    path = (body.path or "").strip()
    if not path:
        raise HTTPException(status_code=400, detail="path 不能为空")
    _manager().remove(path)
    return {"ok": True}


@router.post("/recent/delete_folder")
def recent_delete_folder(body: PathBody):
    """连带删除项目目录 + 从最近列表移除。rmtree 忽略错误，缺目录不抛。"""
    path = (body.path or "").strip()
    if not path:
        raise HTTPException(status_code=400, detail="path 不能为空")
    shutil.rmtree(path, ignore_errors=True)
    _manager().remove(path)
    return {"ok": True}


@router.post("/recent/clear")
def recent_clear():
    """清空最近列表（不动磁盘），返回清掉的条数。"""
    mgr = _manager()
    paths = [p.get("path", "") for p in mgr.load()]
    for p in paths:
        if p:
            mgr.remove(p)
    return {"ok": True, "cleared": len(paths)}


# ---------- /project/overview ----------

# manifest 四阶段 → overview.html 7 阶段映射。manifest 只有 screenwriter/assets/
# storyboard/production；UI 把 production 细分为 imggen/video/audio/final。
# 这里把 production 的 state 同时投射到后四格，统计量按 episodes 进度填。
_STAGE_LABELS = {
    "ideate": "创意立意",
    "script": "剧本",
    "storyboard": "分镜",
    "imggen": "出图",
    "video": "视频生成",
    "audio": "配音配乐",
    "final": "成片",
}

# manifest state(pending|in_progress|completed) → overview 状态(lock|cur|done)
_STATE_TO_ST = {
    "completed": "done",
    "in_progress": "cur",
    "pending": "lock",
}


def _count_images(proj_dir: Path) -> int:
    """统计项目下已出图数量（递归 images/ 与 prompts 产物外的 .png/.jpg）。

    粗略：数项目目录下所有常见图片扩展名文件（排除封面等也无妨，仅作概览展示）。
    """
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    try:
        return sum(
            1 for p in proj_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in exts
        )
    except OSError:
        return 0


def _st(state: str) -> str:
    return _STATE_TO_ST.get(state, "lock")


# ---------- /project/clips ----------

# 转场页列目录用：视频 + 图片扩展名（小写匹配）
_VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


@router.get("/project/clips")
def project_clips(project: str, sub: str = ""):
    """列出项目目录（或 project/sub 子目录）下的视频与图片片段。

    转场页用：返回 {clips:[{name,path(posix),kind,size}]}，按文件名排序。
    project 空 → 400；目录不存在 → 空列表（不报错）。
    """
    proj = (project or "").strip()
    if not proj:
        raise HTTPException(status_code=400, detail="project 不能为空")
    base = Path(proj)
    sub_clean = (sub or "").strip()
    target = base / sub_clean if sub_clean else base

    clips: list[dict] = []
    if not target.is_dir():
        return {"clips": clips}

    try:
        entries = sorted(target.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return {"clips": clips}

    for p in entries:
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext in _VIDEO_EXTS:
            kind = "video"
        elif ext in _IMAGE_EXTS:
            kind = "image"
        else:
            continue
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        clips.append({
            "name": p.name,
            "path": p.as_posix(),
            "kind": kind,
            "size": size,
        })
    return {"clips": clips}


@router.get("/project/overview")
def project_overview(project: str):
    """读项目 manifest + 目录统计，聚合概览。project=项目目录。"""
    proj = (project or "").strip()
    if not proj:
        raise HTTPException(status_code=400, detail="project 不能为空")
    proj_dir = Path(proj)
    if not proj_dir.exists():
        raise HTTPException(status_code=404, detail=f"项目路径不存在: {proj}")

    m = load_manifest(proj_dir)

    # 集数：episodes 数；缺则看 params.episodes
    episode_count = len(m.episodes) or int(m.params.get("episodes") or 0)
    # 分镜数：episodes.shots_done 累计（去重已在 manifest 内保证）
    shots_done_total = sum(len(e.shots_done) for e in m.episodes.values())
    images_done = _count_images(proj_dir)
    aspect = str(m.params.get("aspect") or m.params.get("aspect_ratio") or "16:9")

    sw_state = m.stage_state("screenwriter")
    assets_state = m.stage_state("assets")
    storyboard_state = m.stage_state("storyboard")
    prod_state = m.stage_state("production")

    stages = [
        {"key": "ideate", "label": _STAGE_LABELS["ideate"],
         "status": _st(sw_state),
         "done": 1 if sw_state == "completed" else 0, "total": 1,
         "meta": "题材/风格" + ("已定" if sw_state == "completed" else "待定")},
        {"key": "script", "label": _STAGE_LABELS["script"],
         "status": _st(sw_state),
         "done": episode_count if sw_state == "completed" else 0,
         "total": episode_count,
         "meta": f"{episode_count} 集"},
        {"key": "storyboard", "label": _STAGE_LABELS["storyboard"],
         "status": _st(storyboard_state),
         "done": shots_done_total, "total": shots_done_total,
         "meta": "分镜脚本"},
        {"key": "imggen", "label": _STAGE_LABELS["imggen"],
         "status": _st(prod_state),
         "done": images_done, "total": shots_done_total,
         "meta": f"{images_done}/{shots_done_total} 已出图"},
        {"key": "video", "label": _STAGE_LABELS["video"],
         "status": _st(prod_state),
         "done": sum(1 for e in m.episodes.values() if e.video_done),
         "total": episode_count, "meta": "图生视频 · 按镜"},
        {"key": "audio", "label": _STAGE_LABELS["audio"],
         "status": _st(prod_state),
         "done": 0, "total": episode_count, "meta": "配音 / 配乐"},
        {"key": "final", "label": _STAGE_LABELS["final"],
         "status": _st(prod_state),
         "done": 0, "total": episode_count, "meta": "合成导出"},
    ]

    # next_action：取第一个非 completed 阶段的 next_action（manifest 显式优先）
    next_action = ""
    for nm in ("screenwriter", "assets", "storyboard", "production"):
        sst = m.pipeline.get(nm)
        if sst is not None and sst.state != "completed" and sst.next_action:
            next_action = sst.next_action
            break

    return {
        "project": {
            "project_id": m.project_id,
            "project_name": m.project_name,
            "path": str(proj_dir),
            "genre": m.genre,
            "aspect": aspect,
            "episode_count": episode_count,
            "shots_total": shots_done_total,
            "images_done": images_done,
            "status": m.status,
            "last_modified": m.last_modified,
        },
        "stages": stages,
        "next_action": next_action,
        "bible": m.style_bible,
        "genre": m.genre,
    }
