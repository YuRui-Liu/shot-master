"""SSE 事件序列化（与 screenwriter_agent.core.sse 同形，中文直出）。"""
from __future__ import annotations

import json
from typing import Any


def sse_event(event: str, data: Any) -> str:
    """构造一个 SSE 块：event: <name>\\ndata: <json>\\n\\n。"""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"
