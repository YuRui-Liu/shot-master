"""资源库 RefImageGenerator 服务（波次1 · A4）。

把「题材/风格驱动」出图链路收敛成一个**纯逻辑、可注入**的服务：
给定 资源类(kind) + 稳定名(name) + 底图 prompt + 风格 id，组装风格注入后的
ref 阶段 prompt，经 compass 任务调度落盘 ref 图，并登记进 ref_index。

设计要点（照 spec「注入契约」+ research §4.3 指纹分层 + §6.4 worker 收敛）：
- **风格注入走 ref 阶段**：style_bible.inject_style_prompt(base, style, stage='ref')
  → ref_fingerprint(中性平光锁一致性) + prompt_suffix + negative_suffix。
- **出图经 compass 统一链路**：Task(type='image') → ImageProvider(底层) →
  TaskRunner.run_task，完成判定**看 out_path 文件落盘**（非返回值）。
- **底层出图函数可注入**（image_backend: (task, abs_out) -> None）：
  测试塞假函数模拟落盘，**绝不真连网络**；真实接线由调用方把
  make_image_provider(cfg).generate 包成该签名注入。
- **风格加载器可注入**（style_loader: style_id -> dict|None）：默认 get_style。
- **落盘成功才登记 ref_index**：source='ai-generated' / status='ready'，
  追加进 <project_root>/<kind>/ref_index.json（同类多条并入同一份）。

kind 限 characters / scenes / props（资源库三类）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Union

from ..core import style_bible as _style_bible
from ..core.compass.providers import ImageProvider
from ..core.compass.ref_index import load_ref_index, save_ref_index
from ..core.compass.task import STATUS_DONE, Task, TaskRunner

# 资源库三类（与 ref_index 子目录一致）
VALID_KINDS = ("characters", "scenes", "props")

# 底层出图函数协议：(task, abs_out) -> None，自行落盘产物（返回值被忽略）。
ImageBackend = Callable[[Task, Path], None]
# 风格加载器协议：style_id -> 风格实体 dict（缺失返回 None/空）。
StyleLoader = Callable[[str], Optional[dict]]


class RefImageGenerator:
    """资源库出图服务：风格注入 → compass 出图 → 落盘 → 登记 ref_index。

    cfg：图片生成配置（真实接线时透传给 make_image_provider；本服务不直接读网络）。
    project_root：项目根；ref 图与 ref_index.json 相对此根落到 <kind>/ 下。
    image_backend：可注入底层出图 (task, abs_out) -> None；None 时缺省不可用
        （留待波次2 接 make_image_provider；本波次测试均注入假函数）。
    style_loader：可注入风格加载器 style_id -> dict；None 时用 style_bible.get_style。
    """

    def __init__(
        self,
        cfg,
        project_root: Union[str, Path],
        *,
        image_backend: Optional[ImageBackend] = None,
        style_loader: Optional[StyleLoader] = None,
    ) -> None:
        self.cfg = cfg
        self.project_root = Path(project_root)
        self.image_backend = image_backend
        self.style_loader: StyleLoader = style_loader or _style_bible.get_style

    # ---- 单条出图 ----------------------------------------------------

    def generate_ref(
        self,
        kind: str,
        name: str,
        base_prompt: str,
        style_id: str,
        *,
        ref_files: Optional[list[str]] = None,
    ) -> tuple[bool, str]:
        """生成单个资源 ref 图。

        流程：校验 kind → 取风格 → ref 阶段注入 prompt → Task(type=image,
        out_path=<kind>/<name>_ref.png) → ImageProvider+TaskRunner 落盘 →
        done 则登记 ref_index(source='ai-generated', status='ready') 并落盘。

        返回 (True, 绝对路径) 或 (False, 错误说明)。
        """
        if kind not in VALID_KINDS:
            raise ValueError(
                f"非法资源类 kind={kind!r}，仅支持 {VALID_KINDS}"
            )
        if self.image_backend is None:
            return (False, "未注入底层出图函数 image_backend")

        # 1) 风格注入（ref 阶段：含 ref_fingerprint）
        style = self.style_loader(style_id) or {}
        prompt = _style_bible.inject_style_prompt(
            base_prompt, style, stage="ref"
        )

        # 2) 组装 Task 并经 compass 链路出图
        out_rel = f"{kind}/{name}_ref.png"
        task = Task(
            type="image",
            prompt=prompt,
            ref_files=list(ref_files or []),
            out_path=out_rel,
        )
        runner = TaskRunner(
            providers={"image": ImageProvider(self.image_backend, self.project_root)},
            project_root=self.project_root,
        )
        try:
            task = runner.run_task(task)
        except Exception as exc:  # 底层异常归一为失败返回，不外抛
            return (False, f"出图失败：{exc}")

        if task.status != STATUS_DONE:
            return (False, f"出图未落盘：{out_rel}")

        # 3) 落盘成功 → 登记 ref_index（同类并入同一份 ref_index.json）
        kind_dir = self.project_root / kind
        idx = load_ref_index(kind_dir)
        idx.add(
            name,
            f"{name}_ref.png",
            source="ai-generated",
            status="ready",
        )
        save_ref_index(idx, kind_dir)

        return (True, str(self.project_root / out_rel))

    # ---- 批量出图 ----------------------------------------------------

    def batch_generate(
        self,
        kind: str,
        names: list[str],
        base_prompts: dict,
        style_id: str,
    ) -> dict:
        """批量生成多个资源 ref 图。

        names 逐条 generate_ref；base_prompts 缺该 name → 空底图（仍走风格注入）。
        返回 {name: (ok, msg)}（msg 成功为绝对路径、失败为错误说明）。
        """
        result: dict[str, tuple[bool, str]] = {}
        for name in names:
            base = base_prompts.get(name, "")
            result[name] = self.generate_ref(kind, name, base, style_id)
        return result
