"""主软件用的 Agent 客户端：httpx + 简单 SSE 解析。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator

import httpx


def parse_sse_lines(lines: Iterable[str]) -> Iterator[dict]:
    """把 SSE 文本（按行）解析为 {event, data:dict} 序列。"""
    cur_event = ""
    cur_data: list[str] = []
    for ln in lines:
        ln = ln.rstrip("\n").rstrip("\r")
        if not ln:
            if cur_event:
                try:
                    data = json.loads("\n".join(cur_data)) if cur_data else {}
                except Exception:
                    data = {}
                yield {"event": cur_event, "data": data}
            cur_event = ""
            cur_data = []
            continue
        if ln.startswith("event:"):
            cur_event = ln[len("event:"):].strip()
        elif ln.startswith("data:"):
            cur_data.append(ln[len("data:"):].strip())


# 路径前缀 → stage key（决定 cfg.screenwriter_stage_assignments 的 lookup）
_PATH_TO_STAGE = {
    "/ideate/chat":  "ideate",
    "/script":       "script",
    "/storyboard":   "storyboard",
    "/prompts":      "prompts",
    "/video_prompt": "video_prompt",
    "/audio_prompt": "audio_prompt",
}

_PROVIDER_DEFAULT_MODELS = {
    "deepseek": "deepseek-v4-flash",
    "doubao":   "doubao-1-5-thinking-pro-250415",
    "openai":   "gpt-4o-mini",
}


class ScreenwriterClient:
    """主软件单例。负责发请求 + 解析 SSE。

    cfg 注入用途：每次 stream_post 自动按 path 推断 stage，从 cfg 拉对应
    凭据塞到 request body 的 `creds` 字段——单一可信源，避免 env 传播失败、
    僵尸 agent 持旧 env、用户改设置不重启不生效等问题。
    """

    def __init__(self, base_url: str, cfg=None):
        self.base_url = base_url
        self._cfg = cfg

    def _resolve_creds_for_path(self, path: str) -> dict | None:
        """根据 path 找出对应 stage，从 cfg 解析 api_key / base_url / model。
        cfg 没传 → 返 None，agent 端走 env 兜底。"""
        if self._cfg is None:
            return None
        stage = _PATH_TO_STAGE.get(path)
        if stage is None:
            return None
        stage_assigns = getattr(self._cfg, "screenwriter_stage_assignments", {}) or {}
        providers = getattr(self._cfg, "llm_providers", {}) or {}
        assign = stage_assigns.get(stage) or {}
        provider_name = assign.get("provider") or ""
        model = assign.get("model") or ""
        # 兜底 provider：从 llm_providers 里找第一个有 key 的
        if not provider_name:
            for pname in ("deepseek", "doubao", "openai"):
                if (providers.get(pname) or {}).get("api_key"):
                    provider_name = pname
                    break
        if not provider_name:
            return None
        p = providers.get(provider_name) or {}
        api_key = p.get("api_key") or ""
        base_url = p.get("base_url") or ""
        if not model:
            model = _PROVIDER_DEFAULT_MODELS.get(provider_name, "")
        if not api_key:
            return None
        return {"api_key": api_key, "base_url": base_url, "model": model}

    def health(self) -> dict:
        import httpx
        return httpx.get(f"{self.base_url}/health", timeout=3.0).json()

    def scan_project(self, project_dir: Path) -> dict:
        import httpx
        r = httpx.get(f"{self.base_url}/project",
                      params={"dir": str(project_dir)}, timeout=5.0)
        return r.json()

    def ideate_select(self, project_dir: Path, selected_id: str) -> dict:
        import httpx
        r = httpx.post(f"{self.base_url}/ideate/select",
                       json={"project_dir": str(project_dir),
                             "selected_id": selected_id}, timeout=5.0)
        return r.json()

    def stream_post(self, path: str, body: dict,
                    params: dict | None = None) -> Iterator[dict]:
        """POST + SSE 流；yield {event,data} dict。
        params: 可选 query 参数（如 {"purge_downstream":"true"}）。
        body 中如未带 creds，自动从 cfg 注入（按 path 推 stage）。"""
        # 注入凭据 + model：单一可信源是主软件 cfg，agent 端按 body.creds 用
        if "creds" not in body:
            resolved = self._resolve_creds_for_path(path)
            if resolved is not None:
                body["creds"] = {
                    "api_key": resolved["api_key"],
                    "base_url": resolved["base_url"],
                }
                # model 字段 agent 已支持；只在主软件解析出非空时填
                if resolved.get("model") and "model" not in body:
                    body["model"] = resolved["model"]
        with httpx.Client(timeout=None) as c:
            with c.stream("POST", f"{self.base_url}{path}",
                          json=body, params=params or {}) as resp:
                resp.raise_for_status()
                yield from parse_sse_lines(resp.iter_lines())
