"""TimelineModel：视频生成面板的数据模型。

零 Qt 依赖。提供时间轴段、音频段、图片池和全局参数；
支持转换到子项目 A 的 LTXDirectorSpec、序列化到 settings.json、校验。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional


SegmentType = Literal["image", "text"]
DisplayMode = Literal["seconds", "frames"]


@dataclass(frozen=True)
class TimelineSegment:
    """主轨段（image | text）。内部长度一律帧数。"""
    seg_id: str
    segment_type: SegmentType
    length_frames: int
    local_prompt: str = ""
    image_path: Optional[Path] = None
    guide_strength: float = 1.0


@dataclass(frozen=True)
class TimelineAudio:
    """音频段：绝对帧定位。"""
    audio_id: str
    audio_path: Path
    start_frame: int
    length_frames: int


@dataclass
class TimelineModel:
    """时间轴 + 全局参数 + 图片池。可变容器。"""
    segments: list[TimelineSegment] = field(default_factory=list)
    audios: list[TimelineAudio] = field(default_factory=list)
    pool: list[Path] = field(default_factory=list)

    # 全局
    global_prompt: str = ""
    use_global_prompt: bool = True
    frame_rate: int = 24
    display_mode: DisplayMode = "seconds"
    resolution_preset: str = "1280x720 (16:9) (横屏)"
    use_custom_resolution: bool = False
    custom_width: int = 1024
    custom_height: int = 1024
    filename_prefix: str = "spb_video"
