"""POST /ideate/chat (SSE) + /ideate/select。spec §3.3/§3.4。"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from screenwriter_agent.core.atomic_write import atomic_write_text
from screenwriter_agent.core.paths import idea_read_path, idea_write_path
from screenwriter_agent.core.sse import sse_event
from screenwriter_agent.core.template_loader import load_template
from screenwriter_agent.models.requests import IdeateChatReq, IdeateSelectReq

router = APIRouter()


@router.post("/ideate/select")
def ideate_select(req: IdeateSelectReq):
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
    # 优先级 req.model > 主软件 stage_assignments (env SCREENWRITER_IDEATE_MODEL)
    #       > agent 内置 default_models（最后兜底，多半是 doubao 名，不通用）
    model = (req.model
             or os.environ.get("SCREENWRITER_IDEATE_MODEL")
             or cfg.default_models.get("ideate"))

    # 凭据优先级：body > env > default。主软件每次请求把 creds 塞 body
    # 以彻底绕过 env 传播失败/僵尸 agent 持有旧 env 等问题。
    creds = req.creds or None
    body_key = creds.api_key if creds else None
    body_url = creds.base_url if creds else None
    api_key = (body_key
               or os.environ.get("SCREENWRITER_IDEATE_API_KEY")
               or os.environ.get("SCREENWRITER_LLM_API_KEY", ""))
    base_url = (body_url
                or os.environ.get("SCREENWRITER_IDEATE_BASE_URL")
                or os.environ.get("SCREENWRITER_LLM_BASE_URL",
                                   "https://api.deepseek.com"))

    async def gen():
        import logging
        import traceback
        log = logging.getLogger("screenwriter_agent.ideate")
        from screenwriter_agent.core.llm_client import LLMClient
        # 显式 print 让消息一定进入 subprocess stdout → log_f（而不是被 root
        # logger 吞掉），关键诊断信息——key 哪个来源 / 模型名 / base_url
        cred_src = "body" if body_key else (
            "env_stage" if os.environ.get("SCREENWRITER_IDEATE_API_KEY")
            else ("env_legacy" if os.environ.get("SCREENWRITER_LLM_API_KEY") else "EMPTY"))
        print(f"[ideate] req: model={model!r} base_url={base_url!r} "
              f"cred_src={cred_src} key_set={bool(api_key)}", flush=True)
        log.warning("[ideate] start: model=%r base_url=%r cred_src=%s key_set=%s",
                     model, base_url, cred_src, bool(api_key))
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
                # 客户端断连 → 立即停止迭代，不再消耗 LLM token
                if await request.is_disconnected():
                    print("[ideate] client disconnected; aborting LLM stream",
                           flush=True)
                    return
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
                idea_path = idea_write_path(project_dir)
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
            tb = traceback.format_exc()
            # print → 子进程 stdout → 主软件捕获的日志文件（保底机制）
            print(f"[ideate] EXCEPTION model={model!r} base_url={base_url!r}\n{tb}",
                   flush=True)
            log.error("[ideate] LLM call failed: model=%r base_url=%r\n%s",
                       model, base_url, tb)
            yield sse_event("error", {
                "code": "INTERNAL_ERROR",
                "message": f"{type(e).__name__}: {e}",
                "hint": "看 ~/.drama_shot_master/logs/screenwriter_agent.log 末尾 traceback"})

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
