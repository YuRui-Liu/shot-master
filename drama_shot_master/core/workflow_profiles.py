"""工作流 profile 注册表（Qt-free）。

视频生成 profile（WorkflowProfile）：描述 RunningHub 上 ComfyUI 工作流的关键节点 ID +
策略，供 LTXTaskBuilder 按需取值，避免把节点 ID 写死成单一工作流。

音频 profile（AudioWorkflowProfile）：描述 TTS/BGM/SFX 工作流的模板 JSON + 关键节点，
供 settings UI 和 media_agent 路由引用。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_AUDIO_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "comfyui_workflow"


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


@dataclass(frozen=True)
class AudioWorkflowProfile:
    """TTS / BGM / SFX 工作流 profile。

    与视频 WorkflowProfile 不同，音频工作流节点结构差异大，故 key_nodes 用自由 dict：
    语义键名 → 节点号(str)，由具体工作流定义。notes 用于存疑标注。
    """
    key: str
    name: str
    template_filename: str
    key_nodes: dict = field(default_factory=dict)
    notes: str = ""


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

# ── 音频工作流 profile ──────────────────────────────────────────────
# 模板 JSON 均来自项目根 comfyui_workflow/ 目录的真实工作流。
# key_nodes 按语义键 → ComfyUI 节点号（字符串）标注可配置入口。
# 存疑处见各 profile.notes 字段。

AUDIO_PROFILES: dict[str, AudioWorkflowProfile] = {
    "tts_design": AudioWorkflowProfile(
        key="tts_design",
        name="音色设计",
        template_filename="Qwen3 TTS 音色设计_api.json",
        key_nodes={
            "text": "14",               # Text — 生成内容（待合成文本）
            "audio_style": "15",        # Text — 音色风格描述
            "voice_design": "22",       # TDQwen3TTSVoiceDesign — TTS 生成主节点
            "model_loader": "23",       # TDQwen3TTSModelLoader — 模型加载
            "save_audio": "18",         # SaveAudio (FLAC) — 输出
        },
        notes="节点 15(audio_style) 控制音色风格说明；模型路径固定为 Qwen3-TTS-12Hz-1.7B-VoiceDesign。",
    ),
    "tts_clone": AudioWorkflowProfile(
        key="tts_clone",
        name="声音克隆",
        template_filename="TTS2 情感声音克隆_input_switch_api.json",
        key_nodes={
            "text": "4",                # CR Prompt Text — 待合成文本
            "speaker_audio": "10",      # LoadAudio — 说话人参考音频
            "emo_text": "16",           # CR Prompt Text — 情感文本描述
            "emo_audio": "19",          # LoadAudio — 情感参考音频
            "emo_vector": "21",         # CR Prompt Text — 情感向量字符串
            "emotion_selector": "103",  # PrimitiveInt — 情感模式选择器(1-4)
            "run_node": "1",            # IndexTTS2Run — 主执行节点
            "save_audio": "5",          # SaveAudio (FLAC) — 输出
        },
        notes=(
            "情感模式由 ImpactSwitch 节点 104/105/106/107 路由，"
            "selector(#103) 控制：1=默认 2=情感文本 3=情感音频 4=情感向量。"
            "rgthree Fast Groups Bypasser 是纯 UI 节点，RunningHub 无法寻址，"
            "故改用 Switch 切分支。"
        ),
    ),
    "bgm": AudioWorkflowProfile(
        key="bgm",
        name="配BGM (ACE-Step)",
        template_filename="Ace-Step1.5X 配乐_api.json",
        key_nodes={
            "tags_prompt": "94",        # TextEncodeAceStepAudio1.5 — tags/lrc/seed/bpm/duration 入口
            "bpm": "203",               # Int — 每分钟节拍数
            "duration": "205",          # Float — 歌曲时长（秒）
            "seed": "109",              # PrimitiveInt — 随机种子
            "save_audio": "107",        # SaveAudioMP3 — 输出（320k MP3）
        },
        notes=(
            "tags/bpm/duration/seed 均可通过 node_info 覆盖。"
            "lrc 字段可注入歌词（目前留空=纯音乐）。"
            "keyscale/timesignature 分别固定 A minor / 4/4，可按需覆盖。"
        ),
    ),
    "sfx": AudioWorkflowProfile(
        key="sfx",
        name="配SFX (Stable Audio)",
        template_filename="Stable audio 3纯音乐-音效-VFX-One-Shot音频_api.json",
        key_nodes={
            "user_prompt": "92",        # PrimitiveStringMultiline — 用户简短描述（USER_INPUT）
            "duration": "98",           # PrimitiveFloat — 音频时长（秒）
            "enable_reprompt": "97",    # PrimitiveBoolean — 是否启用 LLM 改写 prompt
            "mode_selector": "108",     # easy anythingIndexSwitch — 模式(index): 0=Music 1=Instrument 2=SFX 3=One-shot
            "save_audio_mp3": "78",     # SaveAudioMP3 — MP3 输出
            "save_audio_flac": "102",   # SaveAudio (FLAC) — FLAC 输出
        },
        notes=(
            "工作流内置 Qwen LLM 改写 prompt（节点 91 TextGenerate），"
            "enable_reprompt=true 时启用。mode_selector 的 index 决定 prompt 模板："
            "0=Music 1=Instrument 2=SFX 3=One-shot。"
            "默认 index=2(SFX)，One-shot 用于短音效(1-11s)。"
            "存疑：节点 108 的 index widget 在 RunningHub 覆盖时是否稳定可用。"
        ),
    ),
}


def get_profile(key: str) -> WorkflowProfile:
    return PROFILES.get(key) or PROFILES[DEFAULT_PROFILE_KEY]


def get_audio_profile(key: str) -> Optional[AudioWorkflowProfile]:
    return AUDIO_PROFILES.get(key)


def template_path_for(profile: WorkflowProfile) -> Path:
    return _TEMPLATES_DIR / profile.template_filename


def audio_template_path_for(profile: AudioWorkflowProfile) -> Path:
    return _AUDIO_TEMPLATES_DIR / profile.template_filename


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
