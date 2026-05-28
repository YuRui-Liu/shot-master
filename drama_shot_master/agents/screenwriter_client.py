"""主软件用的 Agent 客户端：httpx + 简单 SSE 解析。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator


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


class ScreenwriterClient:
    """主软件单例。负责发请求 + 解析 SSE。"""

    def __init__(self, base_url: str):
        self.base_url = base_url

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

    def stream_post(self, path: str, body: dict) -> Iterator[dict]:
        """POST + SSE 流；yield {event,data} dict。"""
        import httpx
        with httpx.Client(timeout=None) as c:
            with c.stream("POST", f"{self.base_url}{path}", json=body) as resp:
                resp.raise_for_status()
                yield from parse_sse_lines(resp.iter_lines())
