"""视频生成工作流 profile 注册表（Qt-free）。

每个 profile 描述一个 RunningHub 上的 ComfyUI 工作流的关键节点 ID + 策略，
供 LTXTaskBuilder 按需取值，避免把节点 ID 写死成单一工作流。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


@dataclass(frozen=True)
class WorkflowProfile:
    key: str
    name: str
    template_filename: str
    director_node: str
    save_video_node: str
    noise_node: str
    resolution_node: Optional[str]
    audio_switch_node: Optional[str]
    extras_yaml: Optional[str]


PROFILES: dict[str, WorkflowProfile] = {
    "director": WorkflowProfile(
        key="director", name="导演台",
        template_filename="ltx_director_v23.json",
        director_node="4", save_video_node="32", noise_node="23",
        resolution_node="34", audio_switch_node=None, extras_yaml=None),
    "director_v3": WorkflowProfile(
        key="director_v3",
        name="高清导演台",
        template_filename="ltx_director_v3_api.json",
        director_node="672", save_video_node="683", noise_node="654",
        resolution_node=None, audio_switch_node="687",
        extras_yaml="ltx_v3_extras.yaml"),
}

DEFAULT_PROFILE_KEY = "director"


def get_profile(key: str) -> WorkflowProfile:
    return PROFILES.get(key) or PROFILES[DEFAULT_PROFILE_KEY]


def template_path_for(profile: WorkflowProfile) -> Path:
    return _TEMPLATES_DIR / profile.template_filename


def extras_path_for(profile: WorkflowProfile) -> Optional[Path]:
    if not profile.extras_yaml:
        return None
    return _TEMPLATES_DIR / profile.extras_yaml


def parse_preset_wh(preset: str) -> Optional[tuple[int, int]]:
    """从 "1280x720 (16:9) …" 解析前缀 WxH；解析不出返回 None。"""
    m = re.match(r"\s*(\d+)\s*[x×]\s*(\d+)", preset or "")
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def load_extras(profile: WorkflowProfile) -> list[dict]:
    """读 profile 的 extras yaml，返回 [{node, field, value}, …]；缺失/异常 → []。"""
    p = extras_path_for(profile)
    if p is None or not p.exists():
        return []
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return []
    overrides = data.get("overrides") if isinstance(data, dict) else None
    if not isinstance(overrides, list):
        return []
    out: list[dict] = []
    for o in overrides:
        if isinstance(o, dict) and "node" in o and "field" in o:
            out.append({"node": str(o["node"]), "field": o["field"],
                        "value": o.get("value")})
    return out
