"""把配音输入构造成 RunningHub nodeInfoList（[{nodeId,fieldName,fieldValue}]）。纯函数。"""
from __future__ import annotations

from drama_shot_master.core.tts_profiles import TTSProfile, CLONE_MODES


def build_design_node_info(text: str, style: str, language: str,
                           prof: TTSProfile) -> list[dict]:
    n = prof.nodes
    return [
        {"nodeId": n["text"], "fieldName": "text", "fieldValue": text},
        {"nodeId": n["style"], "fieldName": "text", "fieldValue": style},
        {"nodeId": n["voice_design"], "fieldName": "language", "fieldValue": language},
    ]


def build_clone_node_info(*, text: str, mode: int, emo_alpha: float,
                          speaker_file: str,
                          emo_text: str = "",
                          emo_vector: list | None = None,
                          emo_audio_file: str | None = None,
                          sampling: dict | None = None,
                          prof: TTSProfile) -> list[dict]:
    if mode not in CLONE_MODES:
        raise ValueError(f"未知情感模式: {mode}")
    n = prof.nodes
    branch_role, select_idx = CLONE_MODES[mode]
    branch = n[branch_role]
    items: list[dict] = [
        {"nodeId": n["text"], "fieldName": "prompt", "fieldValue": text},
        {"nodeId": n["speaker_audio"], "fieldName": "audio", "fieldValue": speaker_file},
    ]
    # Switch 选分支：select=模式序号(input1..4 = 模式1..4)
    items.append({"nodeId": n["switch"], "fieldName": "select",
                  "fieldValue": select_idx})
    items.append({"nodeId": branch, "fieldName": "emo_alpha", "fieldValue": emo_alpha})
    if mode == 2:
        items.append({"nodeId": n["emo_text"], "fieldName": "prompt", "fieldValue": emo_text})
    elif mode == 3:
        if not emo_audio_file:
            raise ValueError("模式3 需要 emo_audio_file")
        items.append({"nodeId": n["emo_audio"], "fieldName": "audio",
                      "fieldValue": emo_audio_file})
    elif mode == 4:
        vec = list(emo_vector or [0] * 8)
        items.append({"nodeId": n["emo_vector"], "fieldName": "prompt",
                      "fieldValue": "[" + ", ".join(str(x) for x in vec) + "]"})
    if sampling:
        for k, v in sampling.items():
            items.append({"nodeId": branch, "fieldName": k, "fieldValue": v})
    return items
