"""TimelineModel：视频生成面板的数据模型。

零 Qt 依赖。提供时间轴段、音频段、图片池和全局参数；
支持转换到子项目 A 的 LTXDirectorSpec、序列化到 settings.json、校验。
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from secrets import token_hex
import time
from typing import Literal, Optional


def _gen_id() -> str:
    """模仿 LTX timeline_data 里的 id 格式：13 位毫秒戳 + 5 位 hex 随机。"""
    return f"{int(time.time() * 1000)}{token_hex(3)[:5]}"


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

    # ---------- 增删段 ----------

    def add_image_segment(self, image_path: Path,
                           length_frames: int = 24,
                           local_prompt: str = "") -> str:
        seg = TimelineSegment(
            seg_id=_gen_id(), segment_type="image",
            length_frames=length_frames, local_prompt=local_prompt,
            image_path=image_path,
        )
        self.segments.append(seg)
        return seg.seg_id

    def add_text_segment(self, length_frames: int = 24,
                          local_prompt: str = "") -> str:
        seg = TimelineSegment(
            seg_id=_gen_id(), segment_type="text",
            length_frames=length_frames, local_prompt=local_prompt,
        )
        self.segments.append(seg)
        return seg.seg_id

    def add_audio(self, audio_path: Path,
                   start_frame: int = 0,
                   length_frames: int = 24) -> str:
        a = TimelineAudio(
            audio_id=_gen_id(), audio_path=audio_path,
            start_frame=start_frame, length_frames=length_frames,
        )
        self.audios.append(a)
        return a.audio_id

    def remove_segment(self, seg_id: str) -> bool:
        for i, s in enumerate(self.segments):
            if s.seg_id == seg_id:
                del self.segments[i]
                return True
        return False

    def remove_audio(self, audio_id: str) -> bool:
        for i, a in enumerate(self.audios):
            if a.audio_id == audio_id:
                del self.audios[i]
                return True
        return False

    def reorder_segments(self, ordered_ids: list[str]) -> None:
        by_id = {s.seg_id: s for s in self.segments}
        self.segments = [by_id[i] for i in ordered_ids if i in by_id]

    # ---------- 更新段字段 ----------

    def update_segment(self, seg_id: str, **fields) -> None:
        for i, s in enumerate(self.segments):
            if s.seg_id == seg_id:
                self.segments[i] = replace(s, **fields)
                return

    def update_audio(self, audio_id: str, **fields) -> None:
        for i, a in enumerate(self.audios):
            if a.audio_id == audio_id:
                self.audios[i] = replace(a, **fields)
                return

    # ---------- 图片池 ----------

    def add_to_pool(self, paths: list[Path]) -> int:
        added = 0
        for p in paths:
            if p not in self.pool:
                self.pool.append(p)
                added += 1
        return added

    def clear_pool(self) -> None:
        self.pool.clear()

    def pool_usage(self) -> dict[Path, int]:
        usage: dict[Path, int] = {p: 0 for p in self.pool}
        for s in self.segments:
            if s.image_path and s.image_path in usage:
                usage[s.image_path] += 1
        return usage
