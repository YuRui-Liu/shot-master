"""跨 4 个任务源（3 store + cfg.soundtrack_tasks dict）的只读聚合。
任务中心抽屉消费 snapshot() → 列表分组展示。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TaskRecord:
    kind: str             # "video" | "imggen" | "dub" | "soundtrack"
    task_id: str
    name: str
    status: str           # "生成中" / "失败" / "完成" / "空闲"
    last_result: str      # 输出路径；空串=未出


class TaskAggregator:
    """无事件订阅；调用方按需 snapshot()。"""

    def __init__(self, cfg, video_store, dub_store, imggen_store, managers: dict):
        """managers: {"video": VideoTaskManagerPanel, "dub": ..., "imggen": ...}。
        无对应 manager 时该 kind 的 status 一律返回 "空闲"。
        soundtrack 不传 manager——状态在 cfg.soundtrack_tasks dict 上。"""
        self.cfg = cfg
        self._video_s = video_store
        self._dub_s = dub_store
        self._imggen_s = imggen_store
        self._managers = managers

    def snapshot(self) -> list[TaskRecord]:
        out: list[TaskRecord] = []
        for kind, store in (("video", self._video_s),
                            ("dub", self._dub_s),
                            ("imggen", self._imggen_s)):
            mgr = self._managers.get(kind)
            for t in store.all():
                status = mgr.get_status(t.id) if mgr is not None else "空闲"
                last = getattr(t, "last_result", "") or ""
                out.append(TaskRecord(kind, t.id, t.name, status, last))
        for d in getattr(self.cfg, "soundtrack_tasks", []) or []:
            out.append(TaskRecord(
                "soundtrack",
                d.get("id", ""),
                d.get("name", ""),
                d.get("status", "空闲"),
                d.get("output", "") or "",
            ))
        return out
