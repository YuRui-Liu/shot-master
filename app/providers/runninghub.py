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


import httpx


def _guess_mime(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".mp3": "audio/mpeg", ".wav": "audio/wav", ".flac": "audio/flac",
        ".mp4": "video/mp4", ".mov": "video/quicktime",
    }.get(ext, "application/octet-stream")


class RunningHubClient:
    """RunningHub OpenAPI 裸客户端：封装鉴权 + 5 个核心端点。

    每个方法对应一次 HTTP 调用；调用方负责把它们编排成业务流程。
    """

    def __init__(self, api_key: str,
                 base_url: str = "https://www.runninghub.cn",
                 request_timeout: float = 30.0):
        if not api_key:
            raise RunningHubUnavailable("RUNNINGHUB_API_KEY 未设置")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=request_timeout)

    # ---------- upload ----------

    def upload_file(self, path: Path) -> str:
        """上传一个本地文件，返回 RunningHub 内部 fileName。"""
        if not path.exists():
            raise RunningHubUploadError(f"文件不存在: {path}")
        url = f"{self.base_url}/openapi/v2/media/upload/binary"
        try:
            with path.open("rb") as f:
                resp = self._client.post(
                    url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files={"file": (path.name, f, _guess_mime(path))},
                )
            if resp.status_code >= 400:
                raise RunningHubUploadError(
                    f"upload HTTP {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            if data.get("code") != 0:
                msg = data.get("msg") or data.get("message") or ""
                raise RunningHubUploadError(
                    f"upload code={data.get('code')} msg={msg}")
            return data["data"]["fileName"]
        except httpx.HTTPError as e:
            raise RunningHubUnavailable(f"upload 连接失败: {e}") from e
        except (KeyError, ValueError) as e:
            raise RunningHubUploadError(f"upload 响应异常: {e}") from e
