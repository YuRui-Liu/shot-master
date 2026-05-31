"""成片任务数据模型 + 列表存储。Qt-free，镜像 video_task_store。"""
from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from secrets import token_hex
from typing import Optional


def _gen_task_id() -> str:
    return f"{int(time.time() * 1000)}{token_hex(3)[:5]}"


@dataclass
class ComposeTask:
    id: str
    name: str
    composition: dict
    status: str = "空闲"
    output_mp4: str = ""
    updated_at: float = 0.0

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "composition": self.composition,
                "status": self.status, "output_mp4": self.output_mp4,
                "updated_at": self.updated_at}

    @classmethod
    def from_dict(cls, d: dict) -> "ComposeTask":
        return cls(
            id=str(d.get("id") or _gen_task_id()),
            name=str(d.get("name") or "未命名成片"),
            composition=d.get("composition") or {},
            status=str(d.get("status") or "空闲"),
            output_mp4=str(d.get("output_mp4") or ""),
            updated_at=float(d.get("updated_at") or 0.0),
        )


class ComposeTaskStore:
    def __init__(self, tasks: Optional[list[ComposeTask]] = None):
        self._tasks: list[ComposeTask] = list(tasks or [])

    def all(self) -> list[ComposeTask]:
        return list(self._tasks)

    def get(self, task_id: str) -> Optional[ComposeTask]:
        return next((t for t in self._tasks if t.id == task_id), None)

    def add(self, name: str, composition: dict) -> ComposeTask:
        t = ComposeTask(id=_gen_task_id(), name=name,
                        composition=copy.deepcopy(composition), updated_at=time.time())
        self._tasks.append(t)
        return t

    def update(self, task_id: str, *, name: Optional[str] = None,
               composition: Optional[dict] = None, status: Optional[str] = None,
               output_mp4: Optional[str] = None) -> None:
        t = self.get(task_id)
        if t is None:
            return
        if name is not None:
            t.name = name
        if composition is not None:
            t.composition = copy.deepcopy(composition)
        if status is not None:
            t.status = status
        if output_mp4 is not None:
            t.output_mp4 = output_mp4
        t.updated_at = time.time()

    def remove(self, task_id: str) -> None:
        self._tasks = [t for t in self._tasks if t.id != task_id]

    def to_list(self) -> list[dict]:
        return [t.to_dict() for t in self._tasks]

    @classmethod
    def from_list(cls, data: list[dict]) -> "ComposeTaskStore":
        return cls([ComposeTask.from_dict(d) for d in (data or [])])
