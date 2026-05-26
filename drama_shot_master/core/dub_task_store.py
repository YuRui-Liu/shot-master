"""配音任务的类型化存储 + 持久化（镜像 VideoTaskStore）。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict

from drama_shot_master.core.video_task_store import _gen_task_id


@dataclass
class DubTask:
    id: str
    name: str
    mode: str                       # "design" | "clone"
    payload: dict = field(default_factory=dict)
    updated_at: float = 0.0
    last_result: str = ""


class DubTaskStore:
    def __init__(self, tasks: list[DubTask] | None = None):
        self._tasks: list[DubTask] = list(tasks or [])

    def all(self) -> list[DubTask]:
        return list(self._tasks)

    def get(self, task_id: str) -> DubTask | None:
        return next((t for t in self._tasks if t.id == task_id), None)

    def add(self, name: str, *, mode: str, payload: dict | None = None) -> DubTask:
        t = DubTask(id=_gen_task_id(), name=name, mode=mode,
                    payload=dict(payload or {}), updated_at=time.time())
        self._tasks.append(t)
        return t

    def update(self, task_id: str, **kw) -> None:
        t = self.get(task_id)
        if t is None:
            return
        for k, v in kw.items():
            if hasattr(t, k):
                setattr(t, k, v)
        t.updated_at = time.time()

    def remove(self, task_id: str) -> None:
        self._tasks = [t for t in self._tasks if t.id != task_id]

    def duplicate(self, task_id: str) -> DubTask | None:
        t = self.get(task_id)
        if t is None:
            return None
        return self.add(f"{t.name} 副本", mode=t.mode, payload=dict(t.payload))

    def to_list(self) -> list[dict]:
        return [asdict(t) for t in self._tasks]

    @classmethod
    def from_list(cls, data: list[dict]) -> "DubTaskStore":
        tasks = []
        for d in data or []:
            tasks.append(DubTask(
                id=d.get("id") or _gen_task_id(),
                name=d.get("name", "配音"),
                mode=d.get("mode", "clone"),
                payload=d.get("payload", {}) or {},
                updated_at=d.get("updated_at", 0.0),
                last_result=d.get("last_result", ""),
            ))
        return cls(tasks)
