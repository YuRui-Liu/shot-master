"""R1-T5 · 统一 Task + TaskQueue/TaskRunner 单测（纯逻辑，无 Qt）。

覆盖（照 plan R1-T5 / spec §测试策略 / research §6.4 待决4）：
- Task round-trip（to_dict/from_dict 字段一致）
- TaskRunner 按 type(image|video|dub|music) 路由到注入的 mock provider
- out_path 已存在 → 跳过（幂等返回 done，不重跑 provider）
- type:music scope=project 不绑 episode
- 完成判定看 out_path 文件存在（非进程退出码 / provider 返回值）
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from drama_shot_master.core.compass.task import (
    Task,
    TaskQueue,
    TaskRunner,
)


# ---- mock provider --------------------------------------------------

class _FakeProvider:
    """记录被调用次数；run 时按约定把 out_path 落盘（模拟生成成功）。

    out_path 是相对项目根的路径，故 provider 持有 project_root 以解析绝对路径
    （真实 provider 同理）。write_file=False 模拟「正常返回但未落盘」。
    """

    def __init__(self, project_root: Path, *, write_file: bool = True):
        self.project_root = Path(project_root)
        self.calls: list[Task] = []
        self.write_file = write_file

    def run(self, task: "Task") -> None:
        self.calls.append(task)
        if self.write_file and task.out_path:
            p = self.project_root / task.out_path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("fake-output", encoding="utf-8")


# ---- Task round-trip ------------------------------------------------

def test_task_round_trip():
    t = Task(
        task_id="T-001",
        type="image",
        project_id="P-006",
        episode_id="E1",
        shot_id="S001",
        prompt="一个女主特写",
        ref_files=["characters/女主_ref.png"],
        model_config={"model": "jimeng", "aspect_ratio": "9:16"},
        status="pending",
        out_path="shots/E1/shot001.png",
    )
    d = t.to_dict()
    back = Task.from_dict(d)
    assert back.task_id == "T-001"
    assert back.type == "image"
    assert back.project_id == "P-006"
    assert back.episode_id == "E1"
    assert back.shot_id == "S001"
    assert back.prompt == "一个女主特写"
    assert back.ref_files == ["characters/女主_ref.png"]
    assert back.model_config == {"model": "jimeng", "aspect_ratio": "9:16"}
    assert back.status == "pending"
    assert back.out_path == "shots/E1/shot001.png"


def test_task_from_dict_defaults():
    """缺字段 → 默认值不抛。"""
    t = Task.from_dict({"task_id": "T-9", "type": "video"})
    assert t.task_id == "T-9"
    assert t.type == "video"
    assert t.project_id == ""
    assert t.episode_id is None
    assert t.shot_id is None
    assert t.prompt == ""
    assert t.ref_files == []
    assert t.model_config == {}
    assert t.status == "pending"
    assert t.out_path == ""


def test_task_to_dict_shape():
    t = Task(task_id="T-1", type="image")
    d = t.to_dict()
    for key in (
        "task_id", "type", "project_id", "episode_id", "shot_id",
        "prompt", "ref_files", "model_config", "status", "out_path",
    ):
        assert key in d


# ---- TaskQueue ------------------------------------------------------

def test_queue_submit_and_pop_fifo():
    q = TaskQueue()
    q.submit(Task(task_id="T-1", type="image"))
    q.submit(Task(task_id="T-2", type="video"))
    assert len(q) == 2
    assert q.pop().task_id == "T-1"
    assert q.pop().task_id == "T-2"
    assert q.pop() is None
    assert len(q) == 0


# ---- TaskRunner 按 type 路由 ----------------------------------------

def test_runner_routes_by_type(tmp_path: Path):
    img = _FakeProvider(tmp_path)
    vid = _FakeProvider(tmp_path)
    dub = _FakeProvider(tmp_path)
    mus = _FakeProvider(tmp_path)
    runner = TaskRunner(
        providers={"image": img, "video": vid, "dub": dub, "music": mus},
        project_root=tmp_path,
    )
    runner.run_task(Task(task_id="T-i", type="image", out_path="a.png"))
    runner.run_task(Task(task_id="T-v", type="video", out_path="b.mp4"))
    runner.run_task(Task(task_id="T-d", type="dub", out_path="c.wav"))

    assert len(img.calls) == 1 and img.calls[0].task_id == "T-i"
    assert len(vid.calls) == 1 and vid.calls[0].task_id == "T-v"
    assert len(dub.calls) == 1 and dub.calls[0].task_id == "T-d"
    assert len(mus.calls) == 0


def test_runner_unknown_type_raises(tmp_path: Path):
    runner = TaskRunner(providers={}, project_root=tmp_path)
    with pytest.raises((KeyError, ValueError)):
        runner.run_task(Task(task_id="T-x", type="image", out_path="a.png"))


# ---- 完成判定 = out_path 文件存在 -----------------------------------

def test_completion_judged_by_file_not_return_code(tmp_path: Path):
    """provider 不写文件 → 视为未完成（即便 provider 正常返回）。"""
    prov = _FakeProvider(tmp_path, write_file=False)
    runner = TaskRunner(providers={"image": prov}, project_root=tmp_path)
    result = runner.run_task(Task(task_id="T-i", type="image", out_path="a.png"))
    assert len(prov.calls) == 1
    assert result.status != "done"
    assert result.status == "failed"


def test_completion_done_when_file_written(tmp_path: Path):
    prov = _FakeProvider(tmp_path, write_file=True)
    runner = TaskRunner(providers={"image": prov}, project_root=tmp_path)
    t = Task(task_id="T-i", type="image", out_path="shots/E1/shot001.png")
    result = runner.run_task(t)
    assert result.status == "done"
    assert (tmp_path / "shots/E1/shot001.png").exists()


# ---- 幂等：out_path 已存在 → 跳过 -----------------------------------

def test_idempotent_skip_when_out_path_exists(tmp_path: Path):
    """out_path 已落盘 → 直接返回 done，不再调 provider。"""
    out = tmp_path / "shots" / "E1" / "shot001.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("already-here", encoding="utf-8")

    prov = _FakeProvider(tmp_path)
    runner = TaskRunner(providers={"image": prov}, project_root=tmp_path)
    t = Task(task_id="T-i", type="image", out_path="shots/E1/shot001.png")
    result = runner.run_task(t)

    assert result.status == "done"
    assert len(prov.calls) == 0  # 幂等跳过，未调 provider
    # 原文件未被覆盖
    assert out.read_text(encoding="utf-8") == "already-here"


def test_run_all_drains_queue(tmp_path: Path):
    prov = _FakeProvider(tmp_path)
    runner = TaskRunner(providers={"image": prov}, project_root=tmp_path)
    q = TaskQueue()
    q.submit(Task(task_id="T-1", type="image", out_path="a.png"))
    q.submit(Task(task_id="T-2", type="image", out_path="b.png"))
    results = runner.run_all(q)
    assert len(results) == 2
    assert all(r.status == "done" for r in results)
    assert len(q) == 0


# ---- type:music scope=project 不绑 episode --------------------------

def test_music_task_scope_project_not_bound_to_episode():
    """配乐任务项目级单例：scope=project，不绑 episode/shot。"""
    t = Task(task_id="T-m", type="music", project_id="P-006",
             out_path="soundtrack/soundtrack.json")
    assert t.scope == "project"
    assert t.episode_id is None
    assert t.shot_id is None


def test_non_music_task_scope_episode_default():
    """非配乐任务默认 scope=episode。"""
    t = Task(task_id="T-i", type="image", project_id="P-006", episode_id="E1")
    assert t.scope == "episode"


def test_music_scope_round_trip(tmp_path: Path):
    """music task 落盘读回保持 scope=project。"""
    t = Task(task_id="T-m", type="music", out_path="soundtrack/soundtrack.json")
    back = Task.from_dict(t.to_dict())
    assert back.scope == "project"
    assert back.type == "music"


def test_runner_routes_music(tmp_path: Path):
    mus = _FakeProvider(tmp_path)
    runner = TaskRunner(providers={"music": mus}, project_root=tmp_path)
    t = Task(task_id="T-m", type="music", out_path="soundtrack/soundtrack.json")
    result = runner.run_task(t)
    assert len(mus.calls) == 1
    assert result.status == "done"
