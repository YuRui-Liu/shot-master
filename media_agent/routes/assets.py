"""内容资产端点：题材模板 + 风格圣经。纯逻辑、无网络、无 Qt。

handler 仅调用 core/genre_templates 与 core/style_bible，返回其原始结构
（与 skills 路由调用 core/skill_templates 同构）——后端逻辑在 core，路由只做
HTTP 封装。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from drama_shot_master.core import genre_templates, style_bible

router = APIRouter(prefix="/assets")


# ---------- 题材模板 ----------

@router.get("/genres")
def list_genres_route():
    """返回全部题材 id（读 index.json 登记表）。"""
    return {"genres": genre_templates.list_genres()}


@router.get("/genre")
def genre_detail_route(id: str):
    """单题材模板（yaml -> dict 原结构）。未知 id → 404、空 id → 400。"""
    if not id or not id.strip():
        raise HTTPException(status_code=400, detail="id 不能为空")
    try:
        return genre_templates.load_genre(id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"题材模板不存在: {id}")


# ---------- 风格圣经 ----------

@router.get("/styles")
def list_styles_route():
    """返回全局风格库原始 dict（含 schema_version/default_style_id/styles）。"""
    return style_bible.load_styles()


@router.get("/style")
def style_detail_route(id: str):
    """按 style_id 解析单条风格实体。未知 id → 404、空 id → 400。"""
    if not id or not id.strip():
        raise HTTPException(status_code=400, detail="id 不能为空")
    style = style_bible.get_style(id)
    if style is None:
        raise HTTPException(status_code=404, detail=f"风格不存在: {id}")
    return style
