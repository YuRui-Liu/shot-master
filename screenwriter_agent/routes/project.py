"""GET /project — 扫描项目目录返回阶段状态。"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from screenwriter_agent.core.project_scanner import scan_project

router = APIRouter()


@router.get("/project")
def get_project(dir: str):
    p = Path(dir)
    if not p.is_dir():
        return JSONResponse(
            status_code=400,
            content={"error": {
                "code": "PROJECT_DIR_NOT_FOUND",
                "message": f"path not a directory: {dir}",
                "hint": "选的路径打不开，确认一下是不是被改名或挪走了？",
                "details": {}}})
    st = scan_project(p)
    return {
        "project_dir": st.project_dir,
        "name": st.name,
        "status": st.status,
        "stages": st.stages,
        "recommended_next": st.recommended_next,
        "config_overrides": st.config_overrides,
    }
