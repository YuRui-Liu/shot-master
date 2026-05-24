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

    # ---------- 转 A 的 LTXDirectorSpec ----------

    def to_ltx_spec(self, output_dir: Path):
        """转成子项目 A 的契约对象。use_custom_audio 自动推导。"""
        from app.providers.runninghub import (
            LTXDirectorSpec, LTXSegment, LTXAudioSegment,
        )
        return LTXDirectorSpec(
            global_prompt=self.global_prompt,
            use_global_prompt=self.use_global_prompt,
            segments=tuple(
                LTXSegment(
                    local_prompt=s.local_prompt,
                    length=s.length_frames,
                    image_path=s.image_path,
                    segment_type=s.segment_type,
                    guide_strength=s.guide_strength,
                    seg_id=s.seg_id,
                ) for s in self.segments
            ),
            audio_segments=tuple(
                LTXAudioSegment(
                    audio_path=a.audio_path,
                    start_frame=a.start_frame,
                    length_frames=a.length_frames,
                ) for a in self.audios
            ),
            use_custom_audio=len(self.audios) > 0,
            display_mode=self.display_mode,
            frame_rate=self.frame_rate,
            resolution_preset=self.resolution_preset,
            use_custom_resolution=self.use_custom_resolution,
            custom_width=self.custom_width,
            custom_height=self.custom_height,
            filename_prefix=self.filename_prefix,
            output_dir=output_dir,
        )

    # ---------- 序列化 ----------

    def to_dict(self) -> dict:
        """序列化到可写入 settings.json 的 dict（Path 转 str）。"""
        return {
            "segments": [
                {
                    "seg_id": s.seg_id,
                    "segment_type": s.segment_type,
                    "length_frames": s.length_frames,
                    "local_prompt": s.local_prompt,
                    "image_path": str(s.image_path) if s.image_path else None,
                    "guide_strength": s.guide_strength,
                } for s in self.segments
            ],
            "audios": [
                {
                    "audio_id": a.audio_id,
                    "audio_path": str(a.audio_path),
                    "start_frame": a.start_frame,
                    "length_frames": a.length_frames,
                } for a in self.audios
            ],
            "pool": [str(p) for p in self.pool],
            "global_prompt": self.global_prompt,
            "use_global_prompt": self.use_global_prompt,
            "frame_rate": self.frame_rate,
            "display_mode": self.display_mode,
            "resolution_preset": self.resolution_preset,
            "use_custom_resolution": self.use_custom_resolution,
            "custom_width": self.custom_width,
            "custom_height": self.custom_height,
            "filename_prefix": self.filename_prefix,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TimelineModel":
        """从 settings.json 缓存恢复。缺字段走默认，stale audio 跳过。"""
        m = cls()
        m.segments = [
            TimelineSegment(
                seg_id=s.get("seg_id") or _gen_id(),
                segment_type=s.get("segment_type", "image"),
                length_frames=int(s.get("length_frames", 24)),
                local_prompt=s.get("local_prompt", ""),
                image_path=(Path(s["image_path"])
                            if s.get("image_path") else None),
                guide_strength=float(s.get("guide_strength", 1.0)),
            ) for s in data.get("segments", [])
        ]
        m.audios = [
            TimelineAudio(
                audio_id=a.get("audio_id") or _gen_id(),
                audio_path=Path(a["audio_path"]),
                start_frame=int(a.get("start_frame", 0)),
                length_frames=int(a.get("length_frames", 24)),
            ) for a in data.get("audios", []) if a.get("audio_path")
        ]
        m.pool = [Path(p) for p in data.get("pool", [])]
        m.global_prompt = data.get("global_prompt", "")
        m.use_global_prompt = bool(data.get("use_global_prompt", True))
        m.frame_rate = int(data.get("frame_rate", 24))
        m.display_mode = data.get("display_mode", "seconds")
        m.resolution_preset = data.get(
            "resolution_preset", "1280x720 (16:9) (横屏)")
        m.use_custom_resolution = bool(data.get("use_custom_resolution", False))
        m.custom_width = int(data.get("custom_width", 1024))
        m.custom_height = int(data.get("custom_height", 1024))
        m.filename_prefix = data.get("filename_prefix", "spb_video")
        return m

    # ---------- pre-flight 校验 ----------

    def validate(self) -> tuple[bool, str]:
        """提交前校验。返回 (ok, error_msg)。"""
        if not self.segments:
            return False, "至少需要 1 段画面"
        if not (1 <= self.frame_rate <= 120):
            return False, f"frame_rate（帧率）越界（当前 {self.frame_rate}，需 1-120）"
        for i, s in enumerate(self.segments, start=1):
            if s.length_frames < 1:
                return False, f"段 {i} 长度不合法（{s.length_frames}）"
            if s.segment_type == "image":
                if s.image_path is None:
                    return False, f"段 {i} 是图片段但未绑定图片"
                if not s.image_path.exists():
                    return False, f"段 {i} 图片不存在：{s.image_path}"
            if not (0.0 <= s.guide_strength <= 1.0):
                return False, f"段 {i} guide_strength 越界（{s.guide_strength}）"
        for j, a in enumerate(self.audios, start=1):
            if not a.audio_path.exists():
                return False, f"音频段 {j} 文件不存在：{a.audio_path}"
        return True, ""
