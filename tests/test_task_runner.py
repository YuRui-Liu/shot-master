"""
Task 15: TaskRunner 测试

由于 pytest-asyncio 网络安装受阻，改用 asyncio.run() 包装 async 调用，
行为与 @pytest.mark.asyncio 完全等价。
"""
import asyncio
import pytest
from drama_shot_master.core.task_runner import TaskRunner, TaskItem, TaskEvent


def _make_items(n):
    return [TaskItem(idx=i, payload={"i": i}) for i in range(n)]


async def _collect(runner):
    events = []
    async for ev in runner.stream():
        events.append(ev)
    return events


def test_runner_executes_all_items_serially():
    items = _make_items(3)
    order = []

    async def worker(item):
        order.append(item.idx)
        return {"ok": True, "i": item.payload["i"]}

    runner = TaskRunner(items=items, worker=worker)
    events = asyncio.run(_collect(runner))

    assert order == [0, 1, 2]
    types = [e.type for e in events]
    assert types.count("progress") == 3
    assert types.count("item_done") == 3
    assert types[-1] == "complete"
    complete = events[-1]
    assert complete.payload["ok"] == 3
    assert complete.payload["failed"] == 0


def test_runner_continues_on_item_failure():
    items = _make_items(3)

    async def worker(item):
        if item.idx == 1:
            raise RuntimeError("boom")
        return {"ok": True}

    runner = TaskRunner(items=items, worker=worker)
    events = asyncio.run(_collect(runner))

    item_dones = [e for e in events if e.type == "item_done"]
    assert len(item_dones) == 3
    assert item_dones[1].payload["status"] == "failed"
    assert "boom" in item_dones[1].payload["error"]
    assert item_dones[0].payload["status"] == "ok"
    assert item_dones[2].payload["status"] == "ok"
    complete = events[-1]
    assert complete.payload["ok"] == 2
    assert complete.payload["failed"] == 1


def test_runner_emits_progress_before_each_item():
    items = _make_items(2)

    async def worker(item):
        return {"ok": True}

    runner = TaskRunner(items=items, worker=worker)
    events = asyncio.run(_collect(runner))

    # 期望顺序：progress(0) → item_done(0) → progress(1) → item_done(1) → complete
    assert [e.type for e in events] == [
        "progress", "item_done",
        "progress", "item_done",
        "complete",
    ]
