"""POST /ideate/chat (SSE) + /ideate/select。spec §3.3/§3.4。"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from screenwriter_agent.core.atomic_write import atomic_write_text
from screenwriter_agent.core.downstream import (
    archive_downstream,
    restore_downstream,
)
from screenwriter_agent.core.paths import idea_read_path, idea_write_path
from screenwriter_agent.core.sse import sse_event
from screenwriter_agent.core.template_loader import load_template
from screenwriter_agent.models.requests import IdeateChatReq, IdeateSelectReq

router = APIRouter()


def _title_for(idea: dict, idea_id: str) -> str:
    """从 创意.json candidates 取某 id 的标题；找不到返空串。"""
    for c in idea.get("candidates", []):
        if c.get("id") == idea_id:
            return str(c.get("title") or "")
    return ""


def _record_archive(project_dir, archived: dict | None, idea_id: str,
                    title: str) -> None:
    """把一条归档记录写入 project.json.archive（去重 by idea_id，覆盖更新）。

    manifest 缺失/坏档都不崩——记账失败不影响归档本身（文件已落盘）。
    """
    if not archived or not archived.get("dir"):
        return
    try:
        import time as _t

        from drama_shot_master.core.compass.manifest import (
            load_manifest,
            save_manifest,
        )
        m = load_manifest(project_dir)
        entry = {
            "idea_id": idea_id,
            "title": title,
            "dir": archived["dir"],
            "archived_at": _t.strftime("%Y-%m-%dT%H:%M:%S"),
            "files": list(archived.get("files") or []),
        }
        m.archive = [e for e in m.archive
                     if (e or {}).get("idea_id") != idea_id]
        m.archive.append(entry)
        save_manifest(m, project_dir)
    except Exception:
        # 记账是尽力而为；归档/恢复的真实状态以文件系统为准
        pass


def _clear_archive_record(project_dir, idea_id: str) -> None:
    """恢复某立意后，把它的 archive 记录移除（其产物已回项目根）。"""
    try:
        from drama_shot_master.core.compass.manifest import (
            load_manifest,
            save_manifest,
        )
        m = load_manifest(project_dir)
        new = [e for e in m.archive if (e or {}).get("idea_id") != idea_id]
        if len(new) != len(m.archive):
            m.archive = new
            save_manifest(m, project_dir)
    except Exception:
        pass


def build_ideate_system_content(tpl_text: str, ctx: dict) -> str:
    """组装 ideate system prompt：模板 + context JSON 块 + （非空时）题材规则。

    ②c 题材驱动：ctx['genre_context'] 非空时把题材规则追加到 system_msg 末尾；
    空则与现状完全一致（向后兼容）。"""
    content = (tpl_text + "\n\n## 当前 context\n```json\n"
               + json.dumps(ctx, ensure_ascii=False, indent=2) + "\n```")
    genre_ctx = (ctx.get("genre_context") or "").strip()
    if genre_ctx:
        content += "\n\n## 题材规则\n" + genre_ctx
    return content


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
    prev_selected = idea.get("selected_id")   # 改写前的旧选定（用于判断是否真的换了立意）
    selection_changed = prev_selected != req.selected_id

    archived: dict | None = None
    restored: dict | None = None

    # 换立意（且旧选定非空）→ 先把旧立意的下游产物**归档（绝不删除）**，
    # 再若新立意有归档则恢复其产物。重选同一立意绝不动（防数据丢失）。
    if selection_changed and prev_selected:
        old_title = _title_for(idea, prev_selected)
        res = archive_downstream(p, prev_selected, old_title)
        _record_archive(p, res, prev_selected, old_title)
        if res.get("dir"):
            archived = {"idea_id": prev_selected, "title": old_title,
                        "dir": res["dir"], "files": res["files"]}

    idea["selected_id"] = req.selected_id
    idea["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    atomic_write_text(idea_path, json.dumps(idea, ensure_ascii=False, indent=2))

    if selection_changed:
        restored = restore_downstream(p, req.selected_id)
        if restored.get("files"):
            new_title = _title_for(idea, req.selected_id)
            restored = {"idea_id": req.selected_id, "title": new_title,
                        "files": restored["files"]}
            _clear_archive_record(p, req.selected_id)
        else:
            restored = None

    selected = next(c for c in idea["candidates"] if c["id"] == req.selected_id)
    return {"saved": str(idea_path), "selected": selected,
            "selection_changed": selection_changed,
            "archived": archived, "restored": restored}


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
            system_msg = {"role": "system",
                          "content": build_ideate_system_content(tpl_text, ctx)}
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
    """宽松解析候选。

    主路径：按 '候选 N' 切段（模板 §候选输出格式：`候选 N｜标题：…`）。
    回退1：模板要求候选间用 `---` 分隔——若无 '候选 N' 标记，按 `---` 切块，
            每块含 标题/摘要 即成一候选（容忍 LLM 漏写编号）。
    回退2：仍为空但有正文 → 整段兜底成单候选（保证前端有可选卡片推进，
            不至于因 LLM 不守格式而完全卡死链路）。
    """
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

    # 回退1：按 --- 分隔块
    blocks = [b.strip() for b in re.split(r"\n\s*-{3,}\s*\n", raw) if b.strip()]
    for i, body in enumerate(blocks, 1):
        title = _first_line(body, "标题")
        summary = _extract(body, "摘要|核心")
        if not title and not summary:
            continue
        out.append({"id": f"c{i}", "title": title or f"候选 {i}",
                    "angle": _extract(body, "切入角度"),
                    "summary": summary or body[:120],
                    "highlights": _extract(body, "亮点|看点"),
                    "est_duration": 60})
    if out:
        return out

    # 回退2：整段兜底成单候选（LLM 完全未守格式时仍可选中推进）
    text = raw.strip()
    if text:
        out.append({"id": "c1",
                    "title": _first_line(text, "标题") or text.splitlines()[0][:24],
                    "angle": _extract(text, "切入角度"),
                    "summary": _extract(text, "摘要|核心") or text[:160],
                    "highlights": _extract(text, "亮点|看点"),
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
