"""SFXShot → RunningHub stable_audio_3 workflow node_info_list 映射。

Workflow ID: 2060218796413112321
模板: comfyui_workflow/Stable audio 3纯音乐-音效-VFX-One-Shot音频_api.json

4 个被覆盖的节点：
  92  PrimitiveStringMultiline  .value  ← 用户短描述
  98  PrimitiveFloat            .value  ← 目标时长秒
  108 easy anythingIndexSwitch  .index  ← 2 (SFX 模式)
  84  KSampler                  .seed   ← 随机种子

其它节点保留 workflow 默认（含 qwen3.5-4B 自动 reprompt）。
"""
from __future__ import annotations


def _node_info(prompt: str, duration: float, seed: int) -> list[dict]:
    return [
        {"nodeId": "92",  "fieldName": "value", "fieldValue": str(prompt)},
        {"nodeId": "98",  "fieldName": "value", "fieldValue": float(duration)},
        {"nodeId": "108", "fieldName": "index", "fieldValue": 2},
        {"nodeId": "84",  "fieldName": "seed",  "fieldValue": int(seed)},
    ]
