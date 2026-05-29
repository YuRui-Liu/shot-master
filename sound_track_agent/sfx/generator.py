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
    """轮询任务直到 SUCCESS → 返回 audio fileUrl；FAIL → RuntimeError；超时 → TimeoutError。"""
    deadline = _time.time() + timeout
    while _time.time() < deadline:
        status = client.get_task_status(task_id) or {}
        st = str(status.get("status", "")).upper()
        if st == "SUCCESS":
            outputs = client.get_task_outputs(task_id) or []
            for out in outputs:
                if str(out.get("fileType", "")).lower() in ("mp3", "wav", "audio"):
                    return out["fileUrl"]
            raise RuntimeError(
                f"task {task_id} succeeded but no audio in outputs: {outputs}")
        if st in ("FAILED", "ERROR"):
            raise RuntimeError(f"task {task_id} failed: {status}")
        sleep(poll_interval)
    raise TimeoutError(f"task {task_id} timeout after {timeout}s")


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
