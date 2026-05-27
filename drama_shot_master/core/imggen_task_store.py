"""图片生成任务的类型化存储 + 持久化（镜像 DubTaskStore）。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict

from drama_shot_master.core.video_task_store import _gen_task_id


@dataclass
class ImgGenTask:
    id: str
    name: str
    payload: dict = field(default_factory=dict)
    updated_at: float = 0.0
    last_result: str = ""


class ImgGenTaskStore:
    def __init__(self, tasks: list[ImgGenTask] | None = None):
        self._tasks: list[ImgGenTask] = list(tasks or [])

    def all(self):
        return list(self._tasks)

    def get(self, task_id):
        return next((t for t in self._tasks if t.id == task_id), None)

    def add(self, name: str, *, payload: dict | None = None) -> ImgGenTask:
        t = ImgGenTask(id=_gen_task_id(), name=name,
                       payload=dict(payload or {}), updated_at=time.time())
        self._tasks.append(t)
        return t

    def update(self, task_id, **kw):
        t = self.get(task_id)
        if t is None:
            return
        for k, v in kw.items():
            if hasattr(t, k):
                setattr(t, k, v)
        t.updated_at = time.time()

    def remove(self, task_id):
        self._tasks = [t for t in self._tasks if t.id != task_id]

    def duplicate(self, task_id):
        t = self.get(task_id)
        if t is None:
            return None
        return self.add(f"{t.name} 副本", payload=dict(t.payload))

    def to_list(self):
        return [asdict(t) for t in self._tasks]

    @classmethod
    def from_list(cls, data):
        tasks = [ImgGenTask(id=d.get("id") or _gen_task_id(),
                            name=d.get("name", "图片"),
                            payload=d.get("payload", {}) or {},
                            updated_at=d.get("updated_at", 0.0),
                            last_result=d.get("last_result", ""))
                 for d in (data or [])]
        return cls(tasks)
