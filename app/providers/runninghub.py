"""RunningHub HTTP API 客户端 + LTX 工作流提交器。

独立于 vision providers 与 ComfyUIUpscaler——RunningHub 是远端 SaaS，
封装 5 个 endpoint（upload / create / query / download / cancel），
顶层 submit_ltx_task 串成"提交→轮询→下载"。
"""
from __future__ import annotations


class RunningHubUnavailable(Exception):
    """连接失败 / 服务不可达 / 鉴权缺失。调用方可重试或降级。"""


class RunningHubTaskFailed(Exception):
    """任务执行失败（业务错 / FAILED 状态 / 超时 / 取消）。"""


class RunningHubUploadError(Exception):
    """文件上传失败（本地文件不存在 / 上传 HTTP 错 / 上传业务错）。"""


class RunningHubInvalidSpec(Exception):
    """LTXDirectorSpec 校验失败 / submit 入参非法。"""


from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


SegmentType = Literal["image", "text"]


@dataclass(frozen=True)
class LTXSegment:
    """时间轴上的一段画面：本地图片 + 本段 prompt + 本段时长。"""
    local_prompt: str
    length: int                          # 帧数
    image_path: Path | None = None       # None 表示纯文本段（占时长不占图）
    segment_type: SegmentType = "image"
    guide_strength: float = 1.0          # 0.0~1.0
    seg_id: str = ""                     # 空 → builder 兜底生成


@dataclass(frozen=True)
class LTXAudioSegment:
    """时间轴上的一段音频。"""
    audio_path: Path
    start_frame: int
    length_frames: int


@dataclass(frozen=True)
class LTXDirectorSpec:
    """一次 LTX 视频生成提交的完整用户态参数。

    字段语义与 LTXDirector 节点 (id=46) 的 inputs 对齐。
    """
    # 提示词
    global_prompt: str = ""
    use_global_prompt: bool = True

    # 时间轴
    segments: tuple[LTXSegment, ...] = ()
    audio_segments: tuple[LTXAudioSegment, ...] = ()
    use_custom_audio: bool = False

    # 时长 / 帧率
    display_mode: Literal["seconds", "frames"] = "seconds"
    frame_rate: int = 24

    # 分辨率
    resolution_preset: str = "1280x720 (16:9) (横屏)"
    use_custom_resolution: bool = False
    custom_width: int = 1024
    custom_height: int = 1024

    # 采样
    noise_seed: int | None = None        # None = 用模板默认（固定种子）

    # 输出
    filename_prefix: str = "spb_video"
    output_dir: Path = field(default_factory=lambda: Path("./output"))

    # 其他可调
    epsilon: float = 0.5

    def total_length_frames(self) -> int:
        return sum(s.length for s in self.segments)

    def total_length_seconds(self) -> float:
        return self.total_length_frames() / self.frame_rate

    def unique_local_files(self) -> tuple[Path, ...]:
        """所有需要上传的本地资源路径（去重保序）。"""
        seen: set[Path] = set()
        result: list[Path] = []
        for s in self.segments:
            if s.image_path and s.image_path not in seen:
                seen.add(s.image_path)
                result.append(s.image_path)
        for a in self.audio_segments:
            if a.audio_path not in seen:
                seen.add(a.audio_path)
                result.append(a.audio_path)
        return tuple(result)
