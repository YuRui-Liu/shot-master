"""R3-1 阶段A · compass provider 适配层单测（纯逻辑、无 Qt、绝不真连网络）。

覆盖（照迁移计划 §③ R3-1 / §④ 阶段A「provider 适配层（新增无侵入）」）：
- 4 个薄适配器 ImageProvider/VideoProvider/DubProvider/MusicProvider 各实现统一协议
  run(task: Task) -> out_path(Path)：把 compass.Task 字段翻译成对底层生成函数的调用，
  产物落到 task.out_path 并返回绝对路径。
- 底层生成函数作为可注入依赖（构造时传入），测试用假函数模拟落盘，绝不真连网络。
- out_path 必填校验：缺失 → 报错。
- 可被 TaskRunner 路由：TaskRunner(providers={...}) + run_task 走通；
  假底层写空文件模拟落盘 → 完成判定 done；幂等：已落盘则跳过不再调底层。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from drama_shot_master.core.compass.task import Task, TaskQueue, TaskRunner
from drama_shot_master.core.compass.providers import (
    ImageProvider,
    VideoProvider,
    DubProvider,
    MusicProvider,
)


# ---- 假底层生成函数（记录入参 + 落盘，绝不真连网络）-------------------

class _FakeBackend:
    """模拟底层生成函数：记录每次被调用的 (task, abs_out)，并把产物写到 abs_out。

    write_file=False 模拟「底层正常返回但未落盘」，用于验证完成判定看文件。
    """

    def __init__(self, *, write_file: bool = True):
        self.calls: list[tuple[Task, Path]] = []
        self.write_file = write_file

    def __call__(self, task: Task, abs_out: Path) -> None:
        self.calls.append((task, abs_out))
        if self.write_file:
            abs_out.parent.mkdir(parents=True, exist_ok=True)
            abs_out.write_bytes(b"fake-output")


# ---- 各适配器 run(task) 调底层并返回 out_path -------------------------

@pytest.mark.parametrize(
    "cls, ttype, out_rel",
    [
        (ImageProvider, "image", "shots/E1/shot001.png"),
        (VideoProvider, "video", "shots/E1/shot001.mp4"),
        (DubProvider, "dub", "dub/E1/line001.wav"),
        (MusicProvider, "music", "soundtrack/bgm_final.flac"),
    ],
)
def test_adapter_run_calls_backend_and_returns_out_path(
    tmp_path: Path, cls, ttype, out_rel
):
    backend = _FakeBackend()
    prov = cls(backend, project_root=tmp_path)
    task = Task(task_id="T-1", type=ttype, project_id="P-1", out_path=out_rel)

    result = prov.run(task)

    # 返回 out_path 绝对路径
    assert result == tmp_path / out_rel
    # 调了底层，且把绝对 out_path 传给它
    assert len(backend.calls) == 1
    called_task, called_out = backend.calls[0]
    assert called_task is task
    assert called_out == tmp_path / out_rel
    # 产物落盘
    assert (tmp_path / out_rel).exists()


def test_adapter_run_missing_out_path_raises(tmp_path: Path):
    backend = _FakeBackend()
    prov = ImageProvider(backend, project_root=tmp_path)
    task = Task(task_id="T-1", type="image", out_path="")  # 缺 out_path

    with pytest.raises(ValueError):
        prov.run(task)
    # 缺 out_path 不应触达底层
    assert len(backend.calls) == 0


def test_adapter_run_translates_task_fields(tmp_path: Path):
    """适配器把 Task 字段透传给底层（prompt/ref_files/model_config 可见）。"""
    seen: dict = {}

    def backend(task: Task, abs_out: Path) -> None:
        seen["prompt"] = task.prompt
        seen["ref_files"] = list(task.ref_files)
        seen["model_config"] = dict(task.model_config)
        abs_out.parent.mkdir(parents=True, exist_ok=True)
        abs_out.write_bytes(b"x")

    prov = ImageProvider(backend, project_root=tmp_path)
    task = Task(
        task_id="T-1",
        type="image",
        prompt="女主特写",
        ref_files=["characters/女主_ref.png"],
        model_config={"model": "jimeng"},
        out_path="shots/E1/s.png",
    )
    prov.run(task)
    assert seen["prompt"] == "女主特写"
    assert seen["ref_files"] == ["characters/女主_ref.png"]
    assert seen["model_config"] == {"model": "jimeng"}


# ---- 可被 TaskRunner 路由 + 幂等 -------------------------------------

def test_providers_route_via_task_runner(tmp_path: Path):
    img = ImageProvider(_FakeBackend(), project_root=tmp_path)
    vid = VideoProvider(_FakeBackend(), project_root=tmp_path)
    dub = DubProvider(_FakeBackend(), project_root=tmp_path)
    mus = MusicProvider(_FakeBackend(), project_root=tmp_path)
    runner = TaskRunner(
        providers={"image": img, "video": vid, "dub": dub, "music": mus},
        project_root=tmp_path,
    )

    q = TaskQueue()
    q.submit(Task(task_id="T-i", type="image", out_path="a.png"))
    q.submit(Task(task_id="T-v", type="video", out_path="b.mp4"))
    q.submit(Task(task_id="T-d", type="dub", out_path="c.wav"))
    q.submit(Task(task_id="T-m", type="music", out_path="soundtrack/bgm.flac"))

    results = runner.run_all(q)
    assert [r.status for r in results] == ["done", "done", "done", "done"]
    assert (tmp_path / "a.png").exists()
    assert (tmp_path / "soundtrack/bgm.flac").exists()


def test_runner_idempotent_skips_backend_when_already_done(tmp_path: Path):
    """out_path 已落盘 → TaskRunner 幂等跳过，底层不再被调用。"""
    out = tmp_path / "a.png"
    out.write_bytes(b"already")

    backend = _FakeBackend()
    img = ImageProvider(backend, project_root=tmp_path)
    runner = TaskRunner(providers={"image": img}, project_root=tmp_path)

    result = runner.run_task(Task(task_id="T-i", type="image", out_path="a.png"))
    assert result.status == "done"
    assert len(backend.calls) == 0  # 幂等跳过
    assert out.read_bytes() == b"already"  # 未覆盖


def test_runner_marks_failed_when_backend_does_not_write(tmp_path: Path):
    """底层未落盘 → TaskRunner 完成判定看文件 → failed。"""
    backend = _FakeBackend(write_file=False)
    img = ImageProvider(backend, project_root=tmp_path)
    runner = TaskRunner(providers={"image": img}, project_root=tmp_path)

    result = runner.run_task(Task(task_id="T-i", type="image", out_path="a.png"))
    assert len(backend.calls) == 1
    assert result.status == "failed"
