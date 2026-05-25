"""视频生成任务的数据模型 + 列表存储。

Qt-free，可单测。调用方（main_window）负责把 to_list() 落盘到 settings.json。
"""
from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from secrets import token_hex
from typing import Optional


def _gen_task_id() -> str:
    """13 位毫秒戳 + 5 位 hex 随机，与 timeline 内 id 风格一致。"""
    return f"{int(time.time() * 1000)}{token_hex(3)[:5]}"


@dataclass
class VideoTask:
    id: str
    name: str
    timeline: dict
    updated_at: float = 0.0
    last_result: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "timeline": self.timeline,
            "updated_at": self.updated_at, "last_result": self.last_result,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "VideoTask":
        return cls(
            id=str(d.get("id") or _gen_task_id()),
            name=str(d.get("name") or "未命名任务"),
            timeline=d.get("timeline") or {},
            updated_at=float(d.get("updated_at") or 0.0),
            last_result=str(d.get("last_result") or ""),
        )


class VideoTaskStore:
    """内存维护任务列表。"""

    def __init__(self, tasks: Optional[list[VideoTask]] = None):
        self._tasks: list[VideoTask] = list(tasks or [])

    def all(self) -> list[VideoTask]:
        return list(self._tasks)

    def get(self, task_id: str) -> Optional[VideoTask]:
        return next((t for t in self._tasks if t.id == task_id), None)

    def add(self, name: str, timeline: dict) -> VideoTask:
        t = VideoTask(id=_gen_task_id(), name=name,
                      timeline=copy.deepcopy(timeline), updated_at=time.time())
        self._tasks.append(t)
        return t

    def update(self, task_id: str, *, name: Optional[str] = None,
               timeline: Optional[dict] = None,
               last_result: Optional[str] = None) -> None:
        t = self.get(task_id)
        if t is None:
            return
        if name is not None:
            t.name = name
        if timeline is not None:
            t.timeline = copy.deepcopy(timeline)
        if last_result is not None:
            t.last_result = last_result
        t.updated_at = time.time()

    def remove(self, task_id: str) -> None:
        self._tasks = [t for t in self._tasks if t.id != task_id]

    def duplicate(self, task_id: str) -> Optional[VideoTask]:
        src = self.get(task_id)
        if src is None:
            return None
        return self.add(f"{src.name} 副本", copy.deepcopy(src.timeline))

    def to_list(self) -> list[dict]:
        return [t.to_dict() for t in self._tasks]

    @classmethod
    def from_list(cls, data: list[dict]) -> "VideoTaskStore":
        return cls([VideoTask.from_dict(d) for d in (data or [])])
