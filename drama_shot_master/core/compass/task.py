"""文件罗盘协议 · 统一任务描述符 Task + 单队列 TaskQueue/TaskRunner。

worker 收敛（research §6.4 待决4）：放弃「每功能一套 worker」，统一为
单一任务队列 + 统一 Task 描述符 + 单 TaskRunner 按 type 分发到注入的
provider。完成判定**看 out_path 文件落盘**（非进程退出码 / provider 返回值，
幂等跳过）。配乐 type:music 项目级单例：scope=project、不绑 episode/shot，
落 soundtrack/，同队列不同 scope。

纯逻辑、无 Qt，全单测。字段形状照 research §6.4。
provider 走依赖注入（任意带 `run(task)` 的对象）便于测。
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

# 四种任务类型（对应四类 provider）
TASK_TYPES = ("image", "video", "dub", "music")

# 配乐项目级单例：不绑 episode；其余任务默认绑 episode
SCOPE_PROJECT = "project"
SCOPE_EPISODE = "episode"

# 任务状态
STATUS_PENDING = "pending"
STATUS_DONE = "done"
STATUS_FAILED = "failed"


@dataclass
class Task:
    """统一任务描述符。

    type ∈ {image|video|dub|music}；out_path 是产物落盘相对路径（相对项目根）。
    music 任务项目级单例：scope=project、episode_id/shot_id 置空。
    其余任务 scope=episode。
    """

    task_id: str = ""
    type: str = "image"
    project_id: str = ""
    episode_id: Optional[str] = None
    shot_id: Optional[str] = None
    prompt: str = ""
    ref_files: list[str] = field(default_factory=list)
    model_config: dict = field(default_factory=dict)
    status: str = STATUS_PENDING
    out_path: str = ""

    def __post_init__(self) -> None:
        # music 项目级单例：强制 scope=project 且不绑 episode/shot
        if self.type == "music":
            self.episode_id = None
            self.shot_id = None

    @property
    def scope(self) -> str:
        """music → project（项目级单例）；其余 → episode。"""
        return SCOPE_PROJECT if self.type == "music" else SCOPE_EPISODE

    # ---- 序列化 ------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "type": self.type,
            "project_id": self.project_id,
            "episode_id": self.episode_id,
            "shot_id": self.shot_id,
            "prompt": self.prompt,
            "ref_files": list(self.ref_files),
            "model_config": dict(self.model_config),
            "status": self.status,
            "out_path": self.out_path,
            "scope": self.scope,
        }

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "Task":
        """从 dict 还原；缺字段 → 默认值。scope 由 type 派生，不从 dict 取。"""
        d = d or {}
        return cls(
            task_id=str(d.get("task_id") or ""),
            type=str(d.get("type") or "image"),
            project_id=str(d.get("project_id") or ""),
            episode_id=d.get("episode_id"),
            shot_id=d.get("shot_id"),
            prompt=str(d.get("prompt") or ""),
            ref_files=list(d.get("ref_files") or []),
            model_config=dict(d.get("model_config") or {}),
            status=str(d.get("status") or STATUS_PENDING),
            out_path=str(d.get("out_path") or ""),
        )


class TaskQueue:
    """FIFO 任务队列。submit 入队、pop 出队（空 → None）。"""

    def __init__(self) -> None:
        self._items: deque[Task] = deque()

    def submit(self, task: Task) -> None:
        self._items.append(task)

    def pop(self) -> Optional[Task]:
        if not self._items:
            return None
        return self._items.popleft()

    def __len__(self) -> int:
        return len(self._items)


class TaskRunner:
    """单一调度器：按 type 路由到注入的 provider，完成判定看文件落盘。

    providers：{type: provider}，provider 任意带 `run(task)` 的对象。
    project_root：out_path 相对此根解析为绝对路径。
    """

    def __init__(self, providers: dict, project_root: Union[str, Path]) -> None:
        self.providers = dict(providers or {})
        self.project_root = Path(project_root)

    def _abs_out(self, task: Task) -> Optional[Path]:
        """out_path → 绝对路径；out_path 为空 → None。"""
        if not task.out_path:
            return None
        return self.project_root / task.out_path

    def run_task(self, task: Task) -> Task:
        """执行单任务。

        1. out_path 已存在 → 幂等跳过（标 done，不调 provider）。
        2. 否则按 type 路由到 provider.run(task)。
        3. **完成判定看 out_path 文件存在**（非 provider 返回值）：
           落盘 → done；未落盘 → failed。
        """
        out = self._abs_out(task)

        # 幂等：产物已存在 → 直接 done，不重跑
        if out is not None and out.exists():
            task.status = STATUS_DONE
            return task

        provider = self.providers.get(task.type)
        if provider is None:
            raise KeyError(f"未注册的任务类型 provider: {task.type!r}")

        provider.run(task)

        # 完成判定：看文件是否落盘（非进程退出码 / provider 返回值）
        if out is not None and out.exists():
            task.status = STATUS_DONE
        else:
            task.status = STATUS_FAILED
        return task

    def run_all(self, queue: TaskQueue) -> list[Task]:
        """排空队列，逐个 run_task，返回结果列表。"""
        results: list[Task] = []
        while True:
            task = queue.pop()
            if task is None:
                break
            results.append(self.run_task(task))
        return results
