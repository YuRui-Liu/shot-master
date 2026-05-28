"""POST /ideate/chat (SSE) + /ideate/select。spec §3.3/§3.4。"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from screenwriter_agent.core.atomic_write import atomic_write_text
from screenwriter_agent.core.sse import sse_event
from screenwriter_agent.core.template_loader import load_template
from screenwriter_agent.models.requests import IdeateChatReq, IdeateSelectReq

router = APIRouter()


@router.post("/ideate/select")
def ideate_select(req: IdeateSelectReq):
    p = Path(req.project_dir)
    idea_path = p / "idea.json"
    if not idea_path.is_file():
        return JSONResponse(status_code=400, content={
            "error": {"code": "UPSTREAM_PRODUCT_MISSING",
                      "message": "idea.json not found",
                      "hint": "还没有候选，请先发起创意对话生成候选。"}})
    try:
        idea = json.loads(idea_path.read_text(encoding="utf-8"))
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "error": {"code": "INTERNAL_ERROR",
                      "message": f"idea.json parse: {e}", "hint": ""}})
    ids = {c.get("id") for c in idea.get("candidates", [])}
    if req.selected_id not in ids:
        return JSONResponse(status_code=400, content={
            "error": {"code": "INTERNAL_ERROR",
                      "message": f"selected_id {req.selected_id} not in candidates",
                      "hint": "候选 id 不存在；可能候选已被替换。"}})
    idea["selected_id"] = req.selected_id
    idea["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    atomic_write_text(idea_path, json.dumps(idea, ensure_ascii=False, indent=2))
    selected = next(c for c in idea["candidates"] if c["id"] == req.selected_id)
    return {"saved": str(idea_path), "selected": selected}


@router.post("/ideate/chat")
async def ideate_chat(req: IdeateChatReq, request: Request):
    """SSE：渲染模板 → 喂 LLM → 流式吐出 → done 时落盘 idea.json。"""
    project_dir = Path(req.project_dir)
    if not project_dir.is_dir():
        return JSONResponse(status_code=400, content={
            "error": {"code": "PROJECT_DIR_NOT_FOUND",
                      "message": f"path not found: {req.project_dir}",
                      "hint": "项目目录打不开。"}})

    cfg = request.app.state.cfg
    model = req.model or cfg.default_models.get("ideate")

    async def gen():
        from screenwriter_agent.core.llm_client import LLMClient
        api_key = os.environ.get("SCREENWRITER_LLM_API_KEY", "")
        base_url = os.environ.get("SCREENWRITER_LLM_BASE_URL",
                                  "https://api.deepseek.com")
        try:
            yield sse_event("status", {"phase": "thinking"})
            tpl_text, _src = load_template("ideate", project_dir=project_dir)
            ctx = req.context.model_dump()
            ctx_block = json.dumps(ctx, ensure_ascii=False, indent=2)
            system_msg = {"role": "system", "content":
                          tpl_text + "\n\n## 当前 context\n```json\n"
                          + ctx_block + "\n```"}
            messages = [system_msg] + [m.model_dump() for m in req.messages]
            client = LLMClient(api_key=api_key, base_url=base_url, model=model,
                               reasoning_effort=req.reasoning_effort)

            yield sse_event("status", {"phase": "streaming"})
            acc: list[str] = []
            for chunk in client.stream_chat(messages):
                if chunk.kind == "delta":
                    acc.append(chunk.text)
                    yield sse_event("delta", {"text": chunk.text})
            raw = "".join(acc)

            yield sse_event("status", {"phase": "saving"})
            if req.auto_save_idea_json:
                idea = {
                    "input": req.context.model_dump(),
                    "messages": [m.model_dump() for m in req.messages]
                                + [{"role": "assistant", "content": raw}],
                    "candidates": _parse_candidates_loose(raw),
                    "selected_id": "",
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                idea_path = project_dir / "idea.json"
                atomic_write_text(
                    idea_path, json.dumps(idea, ensure_ascii=False, indent=2))
                yield sse_event("done", {"saved": str(idea_path),
                                          "result": {"candidates": idea["candidates"],
                                                     "raw_text": raw,
                                                     "warnings": []}})
            else:
                yield sse_event("done", {"saved": None,
                                          "result": {"raw_text": raw, "warnings": []}})
        except Exception as e:
            yield sse_event("error", {
                "code": "INTERNAL_ERROR",
                "message": str(e),
                "hint": "出了点意外，再试一次或换模型。"})

    return StreamingResponse(gen(), media_type="text/event-stream")


def _parse_candidates_loose(raw: str) -> list[dict]:
    """MVP 简化解析：按 '候选 N' 切段。精修留 P2。"""
    import re
    out = []
    parts = re.split(r"(?:^|\n)\s*[#＃]*\s*候选\s*([0-9]+)", raw)
    if len(parts) >= 3:
        for i in range(1, len(parts), 2):
            idx = parts[i].strip()
            body = parts[i + 1].strip()
            out.append({"id": f"c{idx}", "title": _first_line(body, "标题"),
                        "angle": _extract(body, "切入角度"),
                        "summary": _extract(body, "摘要|核心"),
                        "highlights": _extract(body, "亮点|看点"),
                        "est_duration": 60})
    return out


def _first_line(text: str, key: str = "") -> str:
    for ln in text.splitlines():
        if key and key in ln:
            return ln.split("：" if "：" in ln else ":", 1)[-1].strip()
    return text.splitlines()[0].strip() if text else ""


def _extract(text: str, key_re: str) -> str:
    import re
    m = re.search(rf"(?:{key_re})\s*[：:]\s*(.+?)(?=\n[#＃]|\n[一二三四]、|\Z)",
                  text, re.DOTALL)
    return m.group(1).strip() if m else ""
