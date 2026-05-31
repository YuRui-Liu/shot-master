"""创作技能端点：列表 / 详情。纯逻辑、无网络、无 Qt。

handler 仅调用 core/skill_templates 的 list_skills()/load_skill(id)
（与 imaging 路由调用 imaging.*、soundtrack 路由调用 sound_track_agent.* 同构）——
后端逻辑在 core，路由只做 HTTP 封装。设计依据 docs/explorer/skills-loader-design.md §4。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from drama_shot_master.core import skill_templates

router = APIRouter(prefix="/skills")


@router.get("/list")
def list_skills_route():
    """返回全部 SkillManifest（前端网格/筛选直接消费）。"""
    return {"skills": skill_templates.list_skills()}


@router.get("/detail")
def detail_route(id: str):
    """单技能详情（含解析后的注入模块清单与正文）。未知 id → 404。"""
    if not id or not id.strip():
        raise HTTPException(status_code=400, detail="id 不能为空")
    try:
        return skill_templates.load_skill(id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"创作技能不存在: {id}")
