"""串行批量执行器 + 事件流。

为 API 层（batch.py）提供 async iterator，每个事件就是 SSE 一行。
失败不中断后续；item_done.status='failed' 时携带 error。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, AsyncIterator


@dataclass
class TaskItem:
    idx: int
    payload: dict
    base_name: str = ""


@dataclass
class TaskEvent:
    type: str            # "progress" | "item_done" | "complete"
    payload: dict


class TaskRunner:
    def __init__(self,
                 items: list[TaskItem],
                 worker: Callable[[TaskItem], Awaitable[dict]]):
        self.items = items
        self.worker = worker

    async def stream(self) -> AsyncIterator[TaskEvent]:
        ok = 0
        failed = 0
        total = len(self.items)
        for item in self.items:
            yield TaskEvent(type="progress", payload={
                "idx": item.idx, "total": total, "base_name": item.base_name,
                "status": "running",
            })
            try:
                result = await self.worker(item)
                ok += 1
                yield TaskEvent(type="item_done", payload={
                    "idx": item.idx, "total": total, "base_name": item.base_name,
                    "status": "ok", "result": result,
                })
            except Exception as e:
                failed += 1
                yield TaskEvent(type="item_done", payload={
                    "idx": item.idx, "total": total, "base_name": item.base_name,
                    "status": "failed", "error": str(e),
                })
        yield TaskEvent(type="complete", payload={"ok": ok, "failed": failed, "total": total})
