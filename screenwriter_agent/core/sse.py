"""SSE 事件序列化 helpers。spec §3.0 事件协议。"""
from __future__ import annotations

import json
from typing import Any


def sse_event(event: str, data: Any) -> str:
    """构造一个 SSE 块：event: <name>\\ndata: <json>\\n\\n。

    data 序列化用 ensure_ascii=False 让中文直出。
    """
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"
