"""单 SFX job 完整生命周期：create_task → poll → download。

镜像 sound_track_agent.music_generator 的 _wait_success / generate_bgm 模式，
输入参数改为 SFX 三元组 (prompt, duration, seed)。
"""
from __future__ import annotations

import time as _time
from pathlib import Path
from typing import Callable

from sound_track_agent.sfx.prompt_composer import _node_info


def _wait_success(client, task_id: str, *, timeout: float = 600.0,
                  poll_interval: float = 5.0,
                  sleep: Callable = _time.sleep) -> str:
    """轮询任务直到 SUCCESS → 返回首个结果 url；FAIL → RuntimeError；超时 → TimeoutError。

    用 RunningHubClient.query_task（与 BGM music_generator 同契约）：
    返回扁平 dict {status, results, errorMessage}，SUCCESS 时 results 为
    [{url, outputType}, ...]。早期版本误用 get_task_status/get_task_outputs
    （client 无此方法）→ AttributeError 被批量生成的失败隔离吞掉 → 远程已
    生成但本地 0 候选。
    """
    waited = 0.0
    while True:
        d = client.query_task(task_id) or {}
        st = str(d.get("status", "")).upper()
        if st == "SUCCESS":
            results = d.get("results") or []
            if not results:
                raise RuntimeError(f"task {task_id} SUCCESS 但无 results")
            return results[0]["url"]
        if st in ("FAILED", "ERROR"):
            raise RuntimeError(
                f"task {task_id} failed: {d.get('errorMessage', '')}")
        if waited >= timeout:
            raise TimeoutError(f"task {task_id} timeout after {timeout}s")
        sleep(poll_interval)
        waited += poll_interval


def generate_sfx(client, workflow_id: str, *, prompt: str, duration: float,
                 seed: int, out_path, timeout: float = 600.0,
                 poll_interval: float = 5.0,
                 sleep: Callable = _time.sleep) -> Path:
    """单 SFX：create → poll → download to out_path → return Path."""
    task_id = client.create_task(
        workflow_id=workflow_id,
        node_info_list=_node_info(prompt, duration, seed))
    url = _wait_success(client, task_id, timeout=timeout,
                        poll_interval=poll_interval, sleep=sleep)
    client.download_file(url, out_path)
    return Path(out_path)
