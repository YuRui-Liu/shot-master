"""文件罗盘协议 · compass provider 适配层（R3-1 阶段A，纯新增零侵入）。

把 worker 收敛（task.py）落地的最后一块：给 `compass.TaskRunner` 注入的
4 类 provider（image/video/dub/music）提供统一协议实现——

    run(task: Task) -> out_path(Path)

每个适配器是**薄壳**：把 `compass.Task` 的字段（prompt/ref_files/model_config）
翻译成对底层生成函数的一次调用，产物落到 `task.out_path`（相对项目根解析为
绝对路径）并返回该绝对路径。

设计要点（照迁移计划 §③ R3-1 / §④ 阶段A）：
- **底层生成函数作为可注入依赖**：构造时传入（任意 `callable(task, abs_out)`），
  便于测试注入假函数模拟落盘，**绝不真连网络**。真实接线时由调用方把
  imggen(make_image_provider().generate) / video(RunningHubClient 提交) /
  dub(tts_submit.submit_and_wait) / music 生成包成 `(task, abs_out) -> None` 注入。
- **out_path 必填校验**：缺失 → ValueError（TaskRunner 完成判定全靠 out_path 落盘，
  无 out_path 无法判完成，是非法任务）。
- **不接面板、不改底层生成函数**：本层只翻译 + 落点，进程退出码/返回值一律不看。

完成判定（文件是否落盘）由 `TaskRunner.run_task` 负责，这里只做翻译 + 触发底层。
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Union

from .task import Task

# 底层生成函数协议：拿到 Task 与解析好的绝对 out_path，自行落盘产物。
# 返回值被忽略（完成判定看文件，不看返回值）。
Backend = Callable[[Task, Path], None]


class _BaseProvider:
    """适配器基类：解析 out_path → 绝对路径、必填校验、调底层、返回 out_path。

    backend：可注入的底层生成函数 `(task, abs_out) -> None`（落盘产物）。
    project_root：out_path 相对此根解析为绝对路径（与 TaskRunner 同一根）。
    """

    def __init__(self, backend: Backend, project_root: Union[str, Path]) -> None:
        self.backend = backend
        self.project_root = Path(project_root)

    def _abs_out(self, task: Task) -> Path:
        """out_path → 绝对路径；缺失 → ValueError（out_path 必填）。"""
        if not task.out_path:
            raise ValueError(
                f"任务 {task.task_id!r}(type={task.type!r}) 缺少 out_path，"
                "无法定位产物落点"
            )
        return self.project_root / task.out_path

    def run(self, task: Task) -> Path:
        """翻译 Task → 调底层落盘 → 返回 out_path 绝对路径。

        out_path 必填；完成判定（文件是否真落盘）交由 TaskRunner。
        """
        abs_out = self._abs_out(task)
        self.backend(task, abs_out)
        return abs_out


class ImageProvider(_BaseProvider):
    """出图适配器：底层接 make_image_provider().generate()（type=image，出图非文本）。"""


class VideoProvider(_BaseProvider):
    """视频适配器：底层接 RunningHubClient 提交并等产物落到 out_path。"""


class DubProvider(_BaseProvider):
    """配音适配器：底层接 tts_submit.submit_and_wait()。"""


class MusicProvider(_BaseProvider):
    """配乐适配器：底层接 music 生成；任务项目级单例，落 soundtrack/。"""
