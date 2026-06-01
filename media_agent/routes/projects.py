"""项目端点：最近列表 / 打开 / 新建。纯逻辑、无 Qt。

- 最近列表 / 打开 走 core/recent_projects.RecentProjectsManager
  （与 UI 的 app_shell 同源：alongside settings.json）。
- 新建走 core/compass/registry.ProjectRegistry 分配稳定身份 P-NNN，
  在 projects_root 下建 P-NNN_slug 目录并登记，同时推进 recent 列表。
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from drama_shot_master.core.compass.registry import ProjectRegistry
from drama_shot_master.core.recent_projects import RecentProjectsManager

router = APIRouter(prefix="/projects")

# 仓库根散文件 settings.json（与 app_shell 的 fallback 一致）；recent_projects.json 同目录
_SETTINGS_PATH = Path("settings.json")

# slug 化：非字母数字与中文压成单个连字符，去首尾连字符
_SLUG_STRIP_RE = re.compile(r"[^0-9A-Za-z一-鿿]+")


def _manager() -> RecentProjectsManager:
    return RecentProjectsManager.alongside_settings(_SETTINGS_PATH)


def _slugify(name: str) -> str:
    s = _SLUG_STRIP_RE.sub("-", name.strip()).strip("-")
    return s or "untitled"


class OpenBody(BaseModel):
    path: str


class CreateBody(BaseModel):
    name: str
    projects_root: str


@router.get("/list")
def list_route():
    """返回最近项目列表（path 仍存在的，最近在前）。"""
    return {"projects": _manager().load()}


@router.post("/open")
def open_route(body: OpenBody):
    """登记/置顶一个已存在项目，返回 {ok, project}。路径不存在 → 404。"""
    path = (body.path or "").strip()
    if not path:
        raise HTTPException(status_code=400, detail="path 不能为空")
    if not Path(path).exists():
        raise HTTPException(status_code=404, detail=f"项目路径不存在: {path}")
    mgr = _manager()
    mgr.push(path)
    project = next(
        (p for p in mgr.load() if p.get("path") == str(Path(path))), None
    )
    return {"ok": True, "project": project}


@router.post("/create")
def create_route(body: CreateBody):
    """在 projects_root 下建 P-NNN_slug 目录并登记，返回 {path}。"""
    name = (body.name or "").strip()
    root_raw = (body.projects_root or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name 不能为空")
    if not root_raw:
        raise HTTPException(status_code=400, detail="projects_root 不能为空")

    projects_root = Path(root_raw)
    projects_root.mkdir(parents=True, exist_ok=True)

    # compass.registry 分配稳定身份 P-NNN（禁硬编码 ID）
    reg = ProjectRegistry(projects_root)
    project_id = reg.allocate_id()
    dir_name = f"{project_id}_{_slugify(name)}"
    proj_dir = projects_root / dir_name
    proj_dir.mkdir(parents=True, exist_ok=True)

    reg.register(
        {
            "project_id": project_id,
            "project_name": name,
            "dir": dir_name + "/",
        }
    )
    reg.save()

    # 推进 recent 列表（push 内部会再同步一次 registry，双轨并存、降级不崩）
    _manager().push(str(proj_dir), name=name)

    return {"path": str(proj_dir), "project_id": project_id}
