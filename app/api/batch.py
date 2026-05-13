"""POST /api/batch — 创建批量任务；GET /api/batch/{id}/stream — SSE 进度流"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import Config
from app.core.output_writer import resolve_output_dir, write_outputs
from app.core.result_parser import parse_result
from app.core.task_runner import TaskItem, TaskRunner
from app.core.template_engine import list_templates, render_template
from app.providers import factory


router = APIRouter()


class BatchRequest(BaseModel):
    folder: str
    template_id: str
    supplement: dict = {}                  # 默认复用同一份
    per_image_supplement: bool = False     # True → 优先查找与图片同名的 .md/.json/.txt
    output_dir: Optional[str] = None
    skip_existing: bool = True
    provider: Optional[str] = None
    model: Optional[str] = None


def _per_image_supplement(img: Path, base: dict) -> dict:
    """寻找与图片同名的 .json / .md / .txt 注入 supplement。"""
    result = dict(base)
    json_p = img.with_suffix(".json")
    if json_p.exists():
        try:
            data = json.loads(json_p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for k, v in data.items():
                    result.setdefault(k, v)
        except Exception:
            pass
    for ext in (".md", ".txt"):
        p = img.with_suffix(ext)
        if p.exists() and not result.get("script"):
            result["script"] = p.read_text(encoding="utf-8")
            break
    return result


@dataclass
class _PendingTask:
    request: BatchRequest
    cfg: Config


_pending: dict[str, _PendingTask] = {}


SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def _list_images(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS)


@router.post("/api/batch")
async def create_batch(req: BatchRequest, request: Request):
    folder = Path(req.folder)
    if not folder.is_dir():
        raise HTTPException(400, f"folder not found: {folder}")
    tpls = [t for t in list_templates(Path("templates")) if t.id == req.template_id]
    if not tpls:
        raise HTTPException(400, f"template '{req.template_id}' not found")

    task_id = uuid.uuid4().hex
    _pending[task_id] = _PendingTask(request=req, cfg=request.app.state.config)
    return {"task_id": task_id}


@router.get("/api/batch/{task_id}/stream")
async def stream_batch(task_id: str):
    if task_id not in _pending:
        raise HTTPException(404, "task not found")
    task = _pending.pop(task_id)
    req = task.request
    cfg = task.cfg

    folder = Path(req.folder)
    images = _list_images(folder)
    tpl = [t for t in list_templates(Path("templates")) if t.id == req.template_id][0]
    out_dir = (Path(req.output_dir) if req.output_dir
               else resolve_output_dir(images[0] if images else None, cfg.default_output_dir))

    provider_name = req.provider or cfg.current_provider
    model = req.model or cfg.current_model

    items = [TaskItem(idx=i, payload={"image": img}, base_name=img.stem)
             for i, img in enumerate(images)]

    async def worker(item: TaskItem) -> dict:
        img: Path = item.payload["image"]
        if req.skip_existing and (out_dir / f"{img.stem}.md").exists() and (out_dir / f"{img.stem}.json").exists():
            return {"status": "skipped", "md_path": str(out_dir / f"{img.stem}.md"),
                    "json_path": str(out_dir / f"{img.stem}.json")}
        effective_supp = (_per_image_supplement(img, req.supplement)
                          if req.per_image_supplement else req.supplement)
        try:
            system_prompt = render_template(tpl, effective_supp)
        except ValueError as e:
            raise RuntimeError(f"template render: {e}")
        provider = factory.build_provider(cfg, provider_name=provider_name, model=model)
        raw = provider.generate([img], system_prompt, "")
        parsed = parse_result(raw)
        md_path, json_path = write_outputs(
            result=parsed, output_dir=out_dir,
            base_name=img.stem, template_id=tpl.id,
            provider=provider_name, model=model,
        )
        return {"md_path": str(md_path), "json_path": str(json_path),
                "global_prompt": parsed.global_prompt}

    runner = TaskRunner(items=items, worker=worker)

    async def event_gen():
        async for ev in runner.stream():
            # worker 返回 status='skipped' 时，把 item_done 的顶级 status 也改成 skipped
            if ev.type == "item_done" and ev.payload.get("status") == "ok":
                inner = ev.payload.get("result", {})
                if isinstance(inner, dict) and inner.get("status") == "skipped":
                    ev.payload["status"] = "skipped"
            payload = json.dumps(ev.payload, ensure_ascii=False)
            yield f"event: {ev.type}\ndata: {payload}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")
