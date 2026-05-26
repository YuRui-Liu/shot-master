"""配音提交编排：上传音频 → create_task → 轮询 → 下载 FLAC。
与 submit_ltx_task 同思路，但音频上传由调用方先做（因 nodeInfoList 里要用 fileName）。"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable


def upload_all(client, paths: list[Path]) -> dict[Path, str]:
    """上传若干本地文件，返回 path -> RunningHub fileName(含 openapi/ 前缀)。"""
    out: dict[Path, str] = {}
    for p in paths:
        p = Path(p)
        out[p] = client.upload_file(p)
    return out


def submit_and_wait(client, *, workflow_id: str, node_info_list: list[dict],
                    upload_paths: list[Path] | None = None,
                    out_path: Path,
                    timeout: float = 1200.0, poll_interval: float = 6.0,
                    progress_cb: Callable[[str], None] | None = None,
                    cancel_check: Callable[[], bool] | None = None) -> Path:
    """注意：若 nodeInfoList 里引用了上传文件的 fileName，调用方应先 upload_all 拿到
    fileName 填进 node_info_list，再调本函数（此处 upload_paths 仅用于"提交前确保已上传"
    的场景，通常传 None）。返回下载到的 FLAC 路径。"""
    if upload_paths:
        upload_all(client, upload_paths)
    task_id = client.create_task(workflow_id=workflow_id, node_info_list=node_info_list)
    deadline = time.time() + timeout
    while True:
        if cancel_check and cancel_check():
            raise RuntimeError("已取消")
        d = client.query_task(task_id)
        status = d.get("status", "UNKNOWN")
        if progress_cb:
            progress_cb(status)
        if status == "SUCCESS":
            results = d.get("results") or []
            if not results:
                raise RuntimeError("任务成功但无输出")
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            return client.download_file(results[0]["url"], out_path)
        if status == "FAILED":
            raise RuntimeError(f"任务失败: {d.get('failedReason') or d.get('errorMessage')}")
        if time.time() > deadline:
            raise RuntimeError("超时")
        if poll_interval:
            time.sleep(poll_interval)
