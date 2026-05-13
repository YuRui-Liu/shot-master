"""模板 CRUD：列表 / 详情 / 创建 / 更新 / 删除 / 推荐"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.template_engine import list_templates, load_template, recommend_template


router = APIRouter()
TEMPLATES_DIR = Path("templates")
ID_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")


class CreateRequest(BaseModel):
    id: str
    raw_markdown: str


class UpdateRequest(BaseModel):
    raw_markdown: str


def _template_to_dict(t) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "body": t.body,
        "suggest_when": t.suggest_when,
        "variables": [
            {
                "name": v.name, "type": v.type, "default": v.default,
                "label": v.label, "required": v.required, "optional": v.optional,
                "options": v.options, "placeholder": v.placeholder,
            }
            for v in t.variables
        ],
        "raw_markdown": t.path.read_text(encoding="utf-8"),
    }


@router.get("/api/templates")
async def list_all():
    return [_template_to_dict(t) for t in list_templates(TEMPLATES_DIR)]


@router.get("/api/templates/recommend")
async def recommend(image_count: int = 1, has_script: bool = False):
    tpls = list_templates(TEMPLATES_DIR)
    matched = recommend_template(tpls, image_count=image_count, has_script=has_script)
    if not matched:
        return {"id": None}
    return _template_to_dict(matched)


@router.get("/api/templates/{tpl_id}")
async def get_one(tpl_id: str):
    p = TEMPLATES_DIR / f"{tpl_id}.md"
    if not p.exists():
        raise HTTPException(404, f"template '{tpl_id}' not found")
    return _template_to_dict(load_template(p))


@router.post("/api/templates")
async def create(req: CreateRequest):
    if not ID_RE.match(req.id):
        raise HTTPException(400, "id may only contain a-z A-Z 0-9 _ -")
    p = TEMPLATES_DIR / f"{req.id}.md"
    if p.exists():
        raise HTTPException(409, f"template '{req.id}' already exists")
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    p.write_text(req.raw_markdown, encoding="utf-8")
    return _template_to_dict(load_template(p))


@router.put("/api/templates/{tpl_id}")
async def update(tpl_id: str, req: UpdateRequest):
    p = TEMPLATES_DIR / f"{tpl_id}.md"
    if not p.exists():
        raise HTTPException(404, f"template '{tpl_id}' not found")
    p.write_text(req.raw_markdown, encoding="utf-8")
    return _template_to_dict(load_template(p))


@router.delete("/api/templates/{tpl_id}")
async def delete(tpl_id: str):
    p = TEMPLATES_DIR / f"{tpl_id}.md"
    if not p.exists():
        raise HTTPException(404, f"template '{tpl_id}' not found")
    p.unlink()
    return {"deleted": tpl_id}
