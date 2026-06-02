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
    _, select_idx = CLONE_MODES[mode]  # branch_role unused: all modes route to IndexTTS2Run node 1
    items: list[dict] = [
        {"nodeId": n["text"], "fieldName": "prompt", "fieldValue": text},
        {"nodeId": n["speaker_audio"], "fieldName": "audio", "fieldValue": speaker_file},
    ]
    # Switch 选分支：PrimitiveInt node 103 "value" = 模式序号 (1=默认/2=文本/3=音频/4=向量)
    # ImpactSwitch 级联 (104-107) 根据此值路由到 IndexTTS2Run
    items.append({"nodeId": n["switch"], "fieldName": "value",
                  "fieldValue": select_idx})
    # 所有模式都通过 IndexTTS2Run (node 1) 执行
    items.append({"nodeId": "1", "fieldName": "emo_alpha", "fieldValue": emo_alpha})
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
            items.append({"nodeId": "1", "fieldName": k, "fieldValue": v})
    return items
