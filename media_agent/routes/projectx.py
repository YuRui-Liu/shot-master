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

import json

from drama_shot_master.core.compass.manifest import load_manifest, save_manifest
from drama_shot_master.core.ffmpeg_locate import probe_video_meta
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


def _validate_rmtree_safe(raw_path: str) -> Path:
    """解析并校验路径是否允许 rmtree 删除。

    防护：拒删根目录、系统关键目录、或以 .. 越权离开项目白名单的路径。
    Path.resolve() 后必须 startswith 当前工作目录或用户主目录（安全白名单），
    否则拒删（403）。
    """
    p = Path(raw_path).resolve()
    # 拒删根目录
    if p == Path(p.anchor):
        raise HTTPException(status_code=403, detail="不允许删除根目录")
    # 拒删系统关键目录（Windows + POSIX 常见）
    _FORBIDDEN = {
        Path("C:/Windows"), Path("C:/Program Files"), Path("C:/Program Files (x86)"),
        Path("C:/System32"), Path("/etc"), Path("/bin"), Path("/usr"), Path("/System"),
    }
    for fb in _FORBIDDEN:
        try:
            r = fb.resolve()
        except Exception:
            continue
        if p == r or str(p).startswith(str(r) + ("\\" if "\\" in str(r) else "/")):
            raise HTTPException(status_code=403, detail=f"不允许删除系统目录: {p}")
    # 安全白名单：当前工作目录 + 用户主目录（项目通常在这些位置下）
    safe = [Path.cwd().resolve(), Path.home().resolve()]
    if not any(str(p).startswith(str(s)) for s in safe):
        raise HTTPException(status_code=403,
                            detail=f"路径 {p} 不在安全白名单内，拒绝删除")
    return p


@router.post("/recent/delete_folder")
def recent_delete_folder(body: PathBody):
    """连带删除项目目录 + 从最近列表移除。rmtree 前校验路径安全性。"""
    raw = (body.path or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="path 不能为空")
    safe_path = _validate_rmtree_safe(raw)
    shutil.rmtree(str(safe_path), ignore_errors=True)
    _manager().remove(raw)
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


# ---------- /project/overview 磁盘扫描（真实产物判定，不信僵尸 manifest） ----------

# 创意阶段产物名（与 screenwriter_agent/core/paths.py 一致，含旧名兼容）
_IDEA_NAMES = ("创意.json", "idea.json")


def _read_idea(proj_dir: Path) -> dict | None:
    """读 创意.json（优先新名，兜底旧名）→ dict；缺失/坏 JSON → None。"""
    for name in _IDEA_NAMES:
        p = proj_dir / name
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError, ValueError):
                return {}
            return data if isinstance(data, dict) else {}
    return None


def _glob_count(proj_dir: Path, *patterns: str) -> int:
    """统计项目根下匹配任一 glob 的文件数（非递归）。"""
    n = 0
    for pat in patterns:
        try:
            n += sum(1 for p in proj_dir.glob(pat) if p.is_file())
        except OSError:
            pass
    return n


def _dir_nonempty(proj_dir: Path, sub: str) -> bool:
    """子目录存在且含至少一个文件/子目录。"""
    d = proj_dir / sub
    try:
        return d.is_dir() and any(d.iterdir())
    except OSError:
        return False


def _scan_stage_states(proj_dir: Path, idea: dict | None) -> dict[str, str]:
    """扫描磁盘真实产物 → 各阶段 done/cur/lock。

    ideate    : 创意.json 存在且 selected_id 非空 → done；存在未选 → cur；无 → lock
    script    : 有 剧本_E*.md 或 剧本.md → done
    storyboard: 有 分镜_E*.json 或 分镜.json → done
    imggen    : prompts/ 目录非空 → done
    video     : video/ 目录有文件 → done
    后四格（imggen/video/audio/final）= production 大阶段，audio/final 暂随 video。
    """
    # ideate
    if idea is None:
        ideate = "lock"
    elif str(idea.get("selected_id") or "").strip():
        ideate = "done"
    else:
        ideate = "cur"

    script_done = _glob_count(proj_dir, "剧本_E*.md", "剧本.md") > 0
    sb_done = _glob_count(proj_dir, "分镜_E*.json", "分镜.json") > 0
    prompts_done = _dir_nonempty(proj_dir, "prompts")
    video_done = _dir_nonempty(proj_dir, "video")

    return {
        "ideate": ideate,
        "script": "done" if script_done else "lock",
        "storyboard": "done" if sb_done else "lock",
        "imggen": "done" if prompts_done else "lock",
        "video": "done" if video_done else "lock",
        "audio": "done" if video_done else "lock",
        "final": "done" if video_done else "lock",
    }


def _episode_count(proj_dir: Path, idea: dict | None) -> int:
    """集数推断：剧本_E*.md 文件数优先；回退创意.json candidate_count/episodes。"""
    n = _glob_count(proj_dir, "剧本_E*.md")
    if n:
        return n
    if (proj_dir / "剧本.md").is_file():
        return 1
    if isinstance(idea, dict):
        inp = idea.get("input") or {}
        if isinstance(inp, dict):
            for key in ("episodes", "episode_count"):
                try:
                    v = int(inp.get(key) or 0)
                except (TypeError, ValueError):
                    v = 0
                if v:
                    return v
    return 0


def _genre_from_idea(idea: dict | None) -> str:
    """从 创意.json input 取 genre：genre / genre_context / genre_tags(join)。"""
    if not isinstance(idea, dict):
        return ""
    inp = idea.get("input") or {}
    if not isinstance(inp, dict):
        return ""
    g = inp.get("genre")
    if isinstance(g, str) and g.strip():
        return g.strip()
    gc = inp.get("genre_context")
    if isinstance(gc, str) and gc.strip():
        return gc.strip()
    tags = inp.get("genre_tags")
    if isinstance(tags, list) and tags:
        return " / ".join(str(t) for t in tags if t)
    return ""


def _bible_from_idea(idea: dict | None):
    """从 创意.json input 取 style_bible：style_bible / style_context / visual_style。

    返回 dict 或字符串（overview.html bibleText 两者都吃）。
    """
    if not isinstance(idea, dict):
        return {}
    inp = idea.get("input") or {}
    if not isinstance(inp, dict):
        return {}
    sb = inp.get("style_bible")
    if isinstance(sb, dict) and sb:
        return sb
    if isinstance(sb, str) and sb.strip():
        return sb
    for key in ("style_context", "visual_style"):
        v = inp.get(key)
        if isinstance(v, str) and v.strip():
            return v
    return {}


def _aspect_from(proj_dir: Path, m, idea: dict | None) -> str:
    """画幅：manifest.params.aspect/aspect_ratio 优先，回退 创意.json input.aspect_ratio。"""
    a = m.params.get("aspect") or m.params.get("aspect_ratio")
    if a:
        return str(a)
    if isinstance(idea, dict):
        inp = idea.get("input") or {}
        if isinstance(inp, dict):
            a = inp.get("aspect_ratio") or inp.get("aspect")
            if a:
                return str(a)
    return "16:9"


# ---------- /project/clips ----------

# 转场页列目录用：视频 + 图片扩展名（小写匹配）
_VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


@router.get("/project/clips")
def project_clips(project: str, sub: str = ""):
    """列出项目目录（或 project/sub 子目录）下的视频与图片片段。

    转场页用：返回 {clips:[{name,path(posix),kind,size,duration,width,height,
    fps,codec,has_audio}]}，按文件名排序。
    视频文件通过 ffprobe 补充元信息（单文件单次调用）；图片字段为默认值。
    每文件独立错误处理：ffprobe 失败时该文件元字段回退为默认值。
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
            "duration": 0.0,
            "width": 0,
            "height": 0,
            "fps": 0.0,
            "codec": "",
            "has_audio": False,
        })
        if kind == "video":
            try:
                meta = probe_video_meta(str(p))
            except Exception:
                meta = {}
            clips[-1].update({
                "duration": meta.get("duration", 0.0),
                "width": meta.get("width", 0),
                "height": meta.get("height", 0),
                "fps": meta.get("fps", 0.0),
                "codec": meta.get("codec", ""),
                "has_audio": meta.get("has_audio", False),
            })
    return {"clips": clips}


@router.get("/project/files")
def project_files(project: str, sub: str = "", ext: str = ""):
    """列出项目目录（或 project/sub 子目录）下的文件，按扩展名可选过滤。

    返回 {files:[{name,path(posix),size}]}，按文件名排序（非递归）。
    - ext：逗号分隔的扩展名（小写、不含点，如 "md,json"）；空则不过滤。
    - project 空 → 400；目录不存在 → 空列表（不报错）。
    """
    proj = (project or "").strip()
    if not proj:
        raise HTTPException(status_code=400, detail="project 不能为空")
    base = Path(proj)
    sub_clean = (sub or "").strip()
    target = base / sub_clean if sub_clean else base

    # 扩展名过滤集合：小写、去点、去空
    ext_set = {
        e.strip().lstrip(".").lower()
        for e in (ext or "").split(",")
        if e.strip()
    }

    files: list[dict] = []
    if not target.is_dir():
        return {"files": files}

    try:
        entries = sorted(target.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return {"files": files}

    for p in entries:
        if not p.is_file():
            continue
        if ext_set and p.suffix.lstrip(".").lower() not in ext_set:
            continue
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        files.append({
            "name": p.name,
            "path": p.as_posix(),
            "size": size,
        })
    return {"files": files}


# next_action：阶段 key → 人类可读下一步建议
_NEXT_ACTION_TEXT = {
    "ideate": "确定题材与立意（创意立意）",
    "script": "生成剧本（剧本创作）",
    "storyboard": "拆解分镜（分镜脚本）",
    "imggen": "按镜出图（图像生成）",
    "video": "图生视频（视频生成）",
    "audio": "配音 / 配乐",
    "final": "合成导出成片",
}

# stages 顺序（next_action 取首个非 done）
_STAGE_ORDER = ("ideate", "script", "storyboard", "imggen", "video", "audio", "final")


@router.get("/project/overview")
def project_overview(project: str):
    """扫描磁盘真实产物 + manifest 元信息，聚合概览。project=项目目录。

    阶段 status 由磁盘产物判定（不信僵尸 manifest pipeline）；
    genre/style_bible/title 优先 manifest（PUT 后权威），回退 创意.json input。
    """
    proj = (project or "").strip()
    if not proj:
        raise HTTPException(status_code=400, detail="project 不能为空")
    proj_dir = Path(proj)
    if not proj_dir.exists():
        raise HTTPException(status_code=404, detail=f"项目路径不存在: {proj}")

    m = load_manifest(proj_dir)
    idea = _read_idea(proj_dir)

    states = _scan_stage_states(proj_dir, idea)
    episode_count = _episode_count(proj_dir, idea)
    sb_total = _glob_count(proj_dir, "分镜_E*.json", "分镜.json")
    images_done = _count_images(proj_dir)

    aspect = _aspect_from(proj_dir, m, idea)
    # genre/style_bible/title：manifest 权威（PUT 后），回退 创意.json input
    genre = m.genre or _genre_from_idea(idea)
    bible = m.style_bible if m.style_bible else _bible_from_idea(idea)
    project_name = m.project_name or proj_dir.name

    ideate_done = states["ideate"] == "done"
    stages = [
        {"key": "ideate", "label": _STAGE_LABELS["ideate"],
         "status": states["ideate"],
         "done": 1 if ideate_done else 0, "total": 1,
         "meta": "题材/风格" + ("已定" if ideate_done else "待定")},
        {"key": "script", "label": _STAGE_LABELS["script"],
         "status": states["script"],
         "done": episode_count if states["script"] == "done" else 0,
         "total": episode_count,
         "meta": f"{episode_count} 集" if episode_count else "等待立意完成"},
        {"key": "storyboard", "label": _STAGE_LABELS["storyboard"],
         "status": states["storyboard"],
         "done": sb_total, "total": sb_total or episode_count,
         "meta": "分镜脚本"},
        {"key": "imggen", "label": _STAGE_LABELS["imggen"],
         "status": states["imggen"],
         "done": images_done, "total": images_done,
         "meta": f"{images_done} 张已出图" if images_done else "按镜出图"},
        {"key": "video", "label": _STAGE_LABELS["video"],
         "status": states["video"],
         "done": _glob_count(proj_dir, "video/*"), "total": episode_count,
         "meta": "图生视频 · 按镜"},
        {"key": "audio", "label": _STAGE_LABELS["audio"],
         "status": states["audio"],
         "done": 0, "total": episode_count, "meta": "配音 / 配乐"},
        {"key": "final", "label": _STAGE_LABELS["final"],
         "status": states["final"],
         "done": 0, "total": episode_count, "meta": "合成导出"},
    ]

    # next_action：首个非 done 阶段（manifest 显式 next_action 优先）
    next_action = ""
    for key in _STAGE_ORDER:
        if states[key] != "done":
            next_action = _NEXT_ACTION_TEXT.get(key, "")
            break
    for nm in ("screenwriter", "assets", "storyboard", "production"):
        sst = m.pipeline.get(nm)
        if sst is not None and sst.state != "completed" and sst.next_action:
            next_action = sst.next_action
            break

    # 全阶段 done 时的兜底：给一个完成态提示
    if not next_action and all(states[k] == "done" for k in _STAGE_ORDER):
        next_action = "全部阶段已完成"
    # 有阶段 lock（未开始）且无其他待办的兜底
    elif not next_action and any(states[k] == "lock" for k in _STAGE_ORDER):
        next_action = "前往「剧本创作」开始新项目"

    return {
        "project": {
            "project_id": m.project_id,
            "project_name": project_name,
            "path": str(proj_dir),
            "genre": genre,
            "aspect": aspect,
            "episode_count": episode_count,
            "shots_total": sb_total,
            "images_done": images_done,
            "status": m.status,
            "last_modified": m.last_modified,
        },
        "stages": stages,
        "next_action": next_action,
        "bible": bible,
        "genre": genre,
    }


# ---------- GET /project/center ----------

@router.get("/project/center")
def project_center():
    """拉取最近项目列表用于项目中心页。

    读取 recent_projects.json，为每个项目聚合 manifest(project_id/genre/status)、
    episode_count、cover.jpg 信息。
    """
    recent = _manager().load()
    projects: list[dict] = []
    for entry in recent:
        proj_path = entry.get("path", "")
        if not proj_path:
            continue
        proj_dir = Path(proj_path)
        if not proj_dir.exists():
            continue

        m = load_manifest(proj_dir)
        idea = _read_idea(proj_dir)
        ep_count = _episode_count(proj_dir, idea)

        # 封面图
        cover_path = proj_dir / "cover.jpg"
        cover = cover_path.as_posix() if cover_path.is_file() else None

        # shot_count：优先 manifest episodes 的 shots_done 总和，兜底 recent 条目
        shot_count = 0
        for ep_progress in m.episodes.values():
            shot_count += len(ep_progress.shots_done)
        if shot_count == 0:
            shot_count = entry.get("shot_count", 0)

        projects.append({
            "name": entry.get("name", proj_dir.name),
            "path": str(proj_dir),
            "project_id": m.project_id,
            "genre": m.genre or _genre_from_idea(idea),
            "episode_count": ep_count,
            "cover": cover,
            "last_opened": entry.get("last_opened", ""),
            "shot_count": shot_count,
            "status": m.status,
        })

    return {"projects": projects, "total": len(projects)}


# ---------- PUT /project/meta ----------

class ProjectMetaBody(BaseModel):
    project: str
    genre: str | None = None
    style_bible: dict | str | None = None
    params: dict | None = None


@router.put("/project/meta")
def project_meta(body: ProjectMetaBody):
    """更新项目 manifest 元信息：load → 按 body 改 genre/style_bible/params → save。

    - project 空 → 400；目录不存在 → 404。
    - style_bible 可为 {ref,name} dict 或字符串（字符串包成 {"description": ...}）。
    - params 浅合并到既有 params。
    """
    proj = (body.project or "").strip()
    if not proj:
        raise HTTPException(status_code=400, detail="project 不能为空")
    proj_dir = Path(proj)
    if not proj_dir.exists():
        raise HTTPException(status_code=404, detail=f"项目路径不存在: {proj}")

    m = load_manifest(proj_dir)

    if body.genre is not None:
        m.genre = body.genre
    if body.style_bible is not None:
        if isinstance(body.style_bible, str):
            m.style_bible = {"description": body.style_bible}
        else:
            m.style_bible = dict(body.style_bible)
    if body.params is not None:
        merged = dict(m.params)
        merged.update(body.params)
        m.params = merged

    save_manifest(m, proj_dir)
    return {"ok": True}
