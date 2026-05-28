"""TTS 工作流 profile：workflow_id + 角色→节点号 映射。节点号默认值来自工作流分析，
可被 cfg 覆盖（见 dub_settings）。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TTSProfile:
    key: str
    name: str
    workflow_id: str
    nodes: dict = field(default_factory=dict)   # 角色 -> 节点号(str)


VOICE_DESIGN = TTSProfile(
    key="voice_design", name="音色设计",
    workflow_id="2059260167811850242",
    nodes={"text": "14", "style": "15", "voice_design": "22"},
)

VOICE_CLONE = TTSProfile(
    key="voice_clone", name="声音克隆",
    workflow_id="2058388078015901697",
    nodes={
        "text": "4", "speaker_audio": "10",
        "emo_text": "16", "emo_audio": "19", "emo_vector": "21",
        "switch": "27",
        "branch_default": "1", "branch_emo_text": "14",
        "branch_emo_audio": "17", "branch_emo_vector": "20",
    },
)

# 情感模式 -> (活动分支角色, Switch 选择序号)
# 分支选择由 ImpactSwitch(节点 #switch)的 select widget 决定：input1..4 = 模式 1..4。
# 注意：rgthree Fast Groups Bypasser 是纯界面节点、不在执行图里，RunningHub 的
# nodeInfoList 无法寻址它，故改用真正在图中的 Switch 节点切分支。
CLONE_MODES = {
    1: ("branch_default", 1),
    2: ("branch_emo_text", 2),
    3: ("branch_emo_audio", 3),
    4: ("branch_emo_vector", 4),
}

# 情感向量分量标签（顺序固定）
EMO_VECTOR_LABELS = ["Happy", "Angry", "Sad", "Fear", "Hate", "Low", "Surprise", "Neutral"]


def with_overrides(prof: TTSProfile, workflow_id: str | None,
                   node_overrides: dict | None) -> TTSProfile:
    """用 cfg 里的覆盖值生成新 profile（不改原对象）。"""
    nodes = dict(prof.nodes)
    if node_overrides:
        nodes.update({k: str(v) for k, v in node_overrides.items()})
    return TTSProfile(prof.key, prof.name,
                      workflow_id or prof.workflow_id, nodes)
