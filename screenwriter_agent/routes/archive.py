"""往期立意归档：GET /project/archives 列举 + POST /project/archive/restore 切回。

端点路径用 ASCII，落盘归档目录仍是中文 归档/<idea_id>__<safe_title>/。
与 /ideate/select 同域（screenwriter_agent），共用 downstream 归档/恢复逻辑。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from screenwriter_agent.core.atomic_write import atomic_write_text
from screenwriter_agent.core.downstream import (
    archive_downstream,
    list_archives,
    restore_downstream,
)
from screenwriter_agent.core.paths import idea_read_path
from screenwriter_agent.models.requests import ArchiveRestoreReq
from screenwriter_agent.routes.ideate import (
    _clear_archive_record,
    _record_archive,
    _title_for,
)

router = APIRouter()


@router.get("/project/archives")
def get_archives(project: str):
    """列出项目归档区的往期立意。当前 selected_id 标 is_active。"""
    p = Path(project)
    if not p.is_dir():
        return JSONResponse(status_code=400, content={
            "error": {"code": "PROJECT_DIR_NOT_FOUND",
                      "message": f"path not a directory: {project}",
                      "hint": "项目目录打不开。"}})
    archives = list_archives(p)
    # 标记当前生效立意（若它恰好也有同 id 归档条目，理论上不会——生效产物在根，
    # 但仍提供 is_active 以满足接口标准；当前 selected 不在归档区，故按 idea_id 匹配）。
    idea_path = idea_read_path(p)
    selected_id = ""
    if idea_path is not None:
        try:
            selected_id = json.loads(
                idea_path.read_text(encoding="utf-8")).get("selected_id") or ""
        except Exception:
            selected_id = ""
    for a in archives:
        a["is_active"] = bool(selected_id) and a["idea_id"] == selected_id
    return {"archives": archives}


@router.post("/project/archive/restore")
def restore_archive(req: ArchiveRestoreReq):
    """显式切回 idea_id：先归档当前 selected 的下游，再恢复 idea_id 的归档产物，
    并把 创意.json.selected_id 设为 idea_id。响应同 /ideate/select 的 archived/restored。"""
    p = Path(req.project_dir)
    idea_path = idea_read_path(p)
    if idea_path is None:
        return JSONResponse(status_code=400, content={
            "error": {"code": "UPSTREAM_PRODUCT_MISSING",
                      "message": "创意.json not found",
                      "hint": "还没有候选，请先发起创意对话生成候选。"}})
    try:
        idea = json.loads(idea_path.read_text(encoding="utf-8"))
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "error": {"code": "INTERNAL_ERROR",
                      "message": f"idea.json parse: {e}", "hint": ""}})
    ids = {c.get("id") for c in idea.get("candidates", [])}
    if req.idea_id not in ids:
        return JSONResponse(status_code=400, content={
            "error": {"code": "INTERNAL_ERROR",
                      "message": f"idea_id {req.idea_id} not in candidates",
                      "hint": "候选 id 不存在；可能候选已被替换。"}})

    prev_selected = idea.get("selected_id")
    selection_changed = prev_selected != req.idea_id

    archived = None
    restored = None

    if selection_changed and prev_selected:
        old_title = _title_for(idea, prev_selected)
        res = archive_downstream(p, prev_selected, old_title)
        _record_archive(p, res, prev_selected, old_title)
        if res.get("dir"):
            archived = {"idea_id": prev_selected, "title": old_title,
                        "dir": res["dir"], "files": res["files"]}

    idea["selected_id"] = req.idea_id
    idea["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    atomic_write_text(idea_path, json.dumps(idea, ensure_ascii=False, indent=2))

    if selection_changed:
        r = restore_downstream(p, req.idea_id)
        if r.get("files"):
            new_title = _title_for(idea, req.idea_id)
            restored = {"idea_id": req.idea_id, "title": new_title,
                        "files": r["files"]}
            _clear_archive_record(p, req.idea_id)

    selected = next(c for c in idea["candidates"] if c["id"] == req.idea_id)
    return {"saved": str(idea_path), "selected": selected,
            "selection_changed": selection_changed,
            "archived": archived, "restored": restored}
