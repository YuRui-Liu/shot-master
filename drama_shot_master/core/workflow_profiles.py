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


def read_image_wh(path) -> Optional[tuple[int, int]]:
    """用 Pillow 读图片真实像素 (宽, 高)；读不到/无 Pillow/任何异常 → None。

    职责单一、绝不抛：调用方据 None 回退到预设分辨率，不崩。
    """
    if path is None:
        return None
    try:
        from PIL import Image
        with Image.open(path) as im:
            w, h = im.size
        if w > 0 and h > 0:
            return int(w), int(h)
        return None
    except Exception:  # noqa: BLE001 — 读图任何异常都回退，绝不让出图流程崩
        return None


def _round_to_multiple(value: int, multiple: int) -> int:
    """把 value 四舍五入到 multiple 的整数倍，且至少为 multiple（>0）。"""
    if multiple <= 0:
        return max(1, value)
    n = max(1, round(value / multiple))
    return n * multiple


def fit_box_to_aspect(width: int, height: int, *,
                      short_side: int = 720,
                      divisible_by: int = 32) -> tuple[int, int]:
    """按给定 (宽,高) 的**宽高比**算出一个外接框，使框宽高比≈输入比，
    短边≈short_side，且两边都对齐到 divisible_by 的整数倍。

    LTXDirector resize_method="maintain aspect ratio" 下 custom_width/height
    是外接框：框比==输入图比 → 不裁切/不 letterbox。短边锚定 short_side 控分辨率。
    入参非法（<=0）时回退到 short_side×short_side 的近似方框。
    """
    if width <= 0 or height <= 0:
        side = _round_to_multiple(short_side, divisible_by)
        return side, side
    if width >= height:           # 横图：高=短边
        h = short_side
        w = round(short_side * width / height)
    else:                          # 竖图：宽=短边
        w = short_side
        h = round(short_side * height / width)
    return _round_to_multiple(w, divisible_by), _round_to_multiple(h, divisible_by)


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
