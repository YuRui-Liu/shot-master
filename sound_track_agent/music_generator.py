"""RunningHub ACE-Step 文生音乐：注入 (tags,bpm,duration,seed) → 候选 BGM。

复用 drama_shot_master.providers.runninghub.RunningHubClient（create_task/query_task/
download_file）。WorkflowID 由调用方传入（spec：2059090557116440578）。
"""
from __future__ import annotations

import time
from pathlib import Path

from sound_track_agent.session import BGMCandidate

# ACE-Step workflow 节点 id（见 spec §11）
NODE_TAGS = "94"     # TextEncodeAceStepAudio1.5.tags
NODE_BPM = "203"     # Int.value（每分钟节拍数）
NODE_DUR = "205"     # Float.value（歌曲时长秒）
NODE_SEED = "109"    # PrimitiveInt.value（随机种子）

_TERMINAL_OK = "SUCCESS"
_TERMINAL_FAIL = "FAILED"


def _node_info(tags: str, bpm: int, duration: float, seed: int) -> list[dict]:
    return [
        {"nodeId": NODE_TAGS, "fieldName": "tags", "fieldValue": tags},
        {"nodeId": NODE_BPM, "fieldName": "value", "fieldValue": int(bpm)},
        {"nodeId": NODE_DUR, "fieldName": "value", "fieldValue": float(duration)},
        {"nodeId": NODE_SEED, "fieldName": "value", "fieldValue": int(seed)},
    ]


def _wait_success(client, task_id: str, *,
                  timeout: float = 600.0, poll_interval: float = 5.0,
                  sleep=time.sleep) -> str:
    """轮询到 SUCCESS，返回首个结果 url。FAILED/超时抛 RuntimeError。"""
    waited = 0.0
    while True:
        d = client.query_task(task_id)
        status = d.get("status")
        if status == _TERMINAL_OK:
            results = d.get("results") or []
            if not results:
                raise RuntimeError(f"task {task_id} SUCCESS 但无 results")
            return results[0]["url"]
        if status == _TERMINAL_FAIL:
            raise RuntimeError(
                f"task {task_id} FAILED: {d.get('errorMessage', '')}")
        if waited >= timeout:
            raise RuntimeError(f"task {task_id} 轮询超时（{timeout}s）")
        sleep(poll_interval)
        waited += poll_interval


def generate_bgm(client, workflow_id: str, *,
                 tags: str, bpm: int, duration: float,
                 out_dir: Path, seeds: list[int],
                 timeout: float = 600.0, poll_interval: float = 5.0,
                 sleep=time.sleep) -> list[BGMCandidate]:
    """对每个 seed 生成一个候选 BGM。返回 BGMCandidate 列表。"""
    out_dir = Path(out_dir)
    candidates: list[BGMCandidate] = []
    for seed in seeds:
        task_id = client.create_task(
            workflow_id=workflow_id,
            node_info_list=_node_info(tags, bpm, duration, seed))
        url = _wait_success(client, task_id, timeout=timeout,
                            poll_interval=poll_interval, sleep=sleep)
        dest = out_dir / f"bgm_seed{seed}.mp3"
        client.download_file(url, dest)
        candidates.append(BGMCandidate(path=str(dest), seed=seed, prompt=tags))
    return candidates
