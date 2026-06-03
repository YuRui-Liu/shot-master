"""RunningHub ACE-Step 文生音乐：注入 (tags,bpm,duration,seed) → 候选 BGM。

复用 drama_shot_master.providers.runninghub.RunningHubClient（create_task/query_task/
download_file）。WorkflowID 由调用方传入（spec：2059090557116440578）。
"""
from __future__ import annotations

import time
from pathlib import Path

from sound_track_agent.session import BGMCandidate

# ACE-Step 1.5 XL 工作流节点 id（对照 Ace-Step1.5X 配乐_api.json）
NODE_TAGS = "94"     # TextEncodeAceStepAudio1.5.tags
# BPM 折入 tags 文字（如 "125BPM"），工作流无独立 BPM 整数节点
NODE_DUR  = "98"     # EmptyAceStep1.5LatentAudio.seconds（控制时长）
NODE_SEED = "109"    # PrimitiveInt.value（随机种子）

_TERMINAL_OK = "SUCCESS"
_TERMINAL_FAIL_SET = {"FAILED", "ERROR", "CANCELLED"}


def _node_info(tags: str, duration: float, seed: int) -> list[dict]:
    """构造 RunningHub 节点注入列表（BPM 已折入 tags 字符串，无独立节点）。"""
    return [
        {"nodeId": NODE_TAGS, "fieldName": "tags",    "fieldValue": tags},
        {"nodeId": NODE_DUR,  "fieldName": "seconds", "fieldValue": float(duration)},
        {"nodeId": NODE_SEED, "fieldName": "value",   "fieldValue": int(seed)},
    ]


def _wait_success(client, task_id: str, *,
                  timeout: float = 600.0, poll_interval: float = 5.0,
                  sleep=time.sleep) -> dict:
    """轮询到 SUCCESS，返回首个 result dict。FAILED/超时抛 RuntimeError，超时前取消任务。"""
    waited = 0.0
    while True:
        d = client.query_task(task_id)
        status = str(d.get("status", "")).upper()
        if status == _TERMINAL_OK:
            results = d.get("results") or []
            if not results:
                raise RuntimeError(f"task {task_id} SUCCESS 但无 results")
            return results[0]
        if status in _TERMINAL_FAIL_SET:
            raise RuntimeError(
                f"task {task_id} {status}: {d.get('errorMessage', '')}")
        if waited >= timeout:
            try:
                client.cancel_task(task_id)
            except Exception:
                pass
            raise RuntimeError(f"task {task_id} 轮询超时（{timeout}s）")
        sleep(poll_interval)
        waited += poll_interval


def generate_bgm(client, workflow_id: str, *,
                 tags: str, bpm: int, duration: float,
                 out_dir: Path, seeds: list[int],
                 timeout: float = 600.0, poll_interval: float = 5.0,
                 sleep=time.sleep) -> list[BGMCandidate]:
    """对每个 seed 生成一个候选 BGM。tags 应已包含 BPM 文字（如 '125BPM'）。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # 确保 BPM 在 tags 里（ACE-Step 文本编码器需要同时看到 BPM 数字）
    bpm_token = f"{int(bpm)}BPM"
    full_tags = tags if bpm_token in tags else f"{tags}, {bpm_token}"
    candidates: list[BGMCandidate] = []
    for seed in seeds:
        task_id = client.create_task(
            workflow_id=workflow_id,
            node_info_list=_node_info(full_tags, duration, seed))
        result = _wait_success(client, task_id, timeout=timeout,
                               poll_interval=poll_interval, sleep=sleep)
        url = result.get("url") or result.get("outputUrl", "")
        # 扩展名从 outputType 推断，ACE-Step 默认输出 wav
        ext = "." + (result.get("outputType") or "wav").lower().lstrip(".")
        dest = out_dir / f"bgm_seed{seed}{ext}"
        client.download_file(url, dest)
        candidates.append(BGMCandidate(path=str(dest), seed=seed, prompt=full_tags))
    return candidates
