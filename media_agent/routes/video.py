"""LTX 视频生成端点：导演台 / 高清导演台。复用 providers.runninghub。

LTX 2.3 支持两种模式（用户强调）：
- mode='director'      → profile key "director"（导演台，节点 4/32/23/34，
                          尊重 settings 自定义模板路径，兜底内置 ltx_director_v23.json）
- mode='hd_director'   → profile key "director_v3"（高清导演台，节点 672/683/654，
                          内置模板 ltx_director_v3_api.json）
两模式各自的 workflow_id 从 cfg.workflow_ids[profile.key] 取；director 还兼容
cfg.runninghub_workflow_id 兜底。profile 由 get_profile(profile.key) 取。

请求体覆盖完整 LTXDirectorSpec 契约（全字段），同时向后兼容旧的窄 body
（prompt/segments[local_prompt,length,image_path]/first_frame/last_frame/
fps/aspect/base_name 仍可用）。新契约字段：
  global_prompt/use_global、segments[prompt,duration_frames|duration_sec,
  guide,first_frame_path,ref_image_path,text]、audio_segments[path,start]、
  use_custom_audio、frame_rate、resolution|custom_w/custom_h、noise_seed、
  epsilon、filename_prefix。

需网络/key 的 RunningHub client 走模块级可注入工厂 _client_factory（默认
build RunningHubClient(cfg)）+ _load_cfg（默认 load_config）；真正的「上传→提交→
轮询→下载」串联封装进可注入的 _submit（默认 submit_ltx_task + handle.wait_for_result），
测试 monkeypatch _client_factory / _submit 注入假实现返回假视频路径，不触网、零 Qt。
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from drama_shot_master.core.workflow_profiles import (
    get_profile, template_path_for,
)
from drama_shot_master.providers.runninghub import (
    LTXDirectorSpec, LTXSegment, LTXAudioSegment, LTXTaskBuilder,
    submit_ltx_task, resolve_template_path,
    RunningHubUnavailable, RunningHubInvalidSpec,
    RunningHubUploadError, RunningHubTaskFailed,
)

router = APIRouter(prefix="/video")


# mode → workflow_profile key
_MODE_PROFILE_KEY = {
    "director": "director",
    "hd_director": "director_v3",
}


def _load_cfg():
    from drama_shot_master.config import load_config
    return load_config()


def _build_video_client(cfg):
    """从 cfg 构造 RunningHub 客户端（LTX 视频生成走它）。"""
    from drama_shot_master.providers.runninghub import RunningHubClient
    return RunningHubClient(
        getattr(cfg, "runninghub_api_key", ""),
        base_url=getattr(cfg, "runninghub_base_url",
                         "https://www.runninghub.cn"))


# 可注入：测试替换为假 client 工厂（不触网）
_client_factory = _build_video_client


def _default_submit(client, spec: LTXDirectorSpec, builder: LTXTaskBuilder, *,
                    workflow_id: str, timeout: float, poll_interval: float
                    ) -> Path:
    """默认实现：submit_ltx_task → handle.wait_for_result()。返回视频文件路径。"""
    handle = submit_ltx_task(client, spec, builder, workflow_id=workflow_id)
    return handle.wait_for_result(timeout=timeout, poll_interval=poll_interval)


# 可注入：测试替换为假实现，返回假视频路径（不触网、不轮询）
_submit = _default_submit


class SegmentIn(BaseModel):
    """时间轴上一段。

    prompt 字段：新契约 ``prompt`` 优先，兼容旧 ``local_prompt``。
    时长：``duration_frames`` 优先；否则 ``duration_sec`` × frame_rate；
          再否则兼容旧 ``length``（帧）。
    参考图：``first_frame_path`` / ``ref_image_path``（任一）优先，
            兼容旧 ``image_path``。
    引导：``guide`` 优先，兼容旧 ``guide_strength``。
    纯文本段：``text=True`` 或显式 ``segment_type='text'`` 或无任何参考图。
    """
    prompt: Optional[str] = None
    local_prompt: Optional[str] = None       # 旧字段别名

    duration_frames: Optional[int] = None    # 帧数（新契约）
    duration_sec: Optional[float] = None      # 秒（新契约，× frame_rate）
    length: Optional[int] = None              # 旧字段别名（帧）

    first_frame_path: Optional[str] = None    # 新契约：首帧参考图
    ref_image_path: Optional[str] = None      # 新契约：参考图（i2v）
    image_path: Optional[str] = None          # 旧字段别名

    text: Optional[bool] = None               # True → 纯文本段
    segment_type: Optional[Literal["image", "text"]] = None

    guide: Optional[float] = None             # 0~1（新契约）
    guide_strength: Optional[float] = None    # 旧字段别名

    seg_id: str = ""

    def _resolved_prompt(self) -> str:
        return (self.prompt if self.prompt is not None
                else self.local_prompt) or ""

    def _resolved_image(self) -> Optional[str]:
        return self.first_frame_path or self.ref_image_path or self.image_path

    def _resolved_length(self, frame_rate: int) -> int:
        if self.duration_frames is not None:
            return max(1, int(self.duration_frames))
        if self.duration_sec is not None:
            return max(1, int(round(self.duration_sec * frame_rate)))
        if self.length is not None:
            return max(1, int(self.length))
        return 1

    def _resolved_guide(self) -> float:
        if self.guide is not None:
            return float(self.guide)
        if self.guide_strength is not None:
            return float(self.guide_strength)
        return 1.0

    def to_segment(self, frame_rate: int) -> LTXSegment:
        img = self._resolved_image()
        # segment_type：显式优先；text=True → text；否则有图为 image、无图为 text
        if self.segment_type is not None:
            seg_type = self.segment_type
        elif self.text:
            seg_type = "text"
        else:
            seg_type = "image" if img else "text"
        return LTXSegment(
            local_prompt=self._resolved_prompt(),
            length=self._resolved_length(frame_rate),
            image_path=Path(img) if (img and seg_type == "image") else None,
            segment_type=seg_type,
            guide_strength=self._resolved_guide(),
            seg_id=self.seg_id,
        )


class AudioSegmentIn(BaseModel):
    """时间轴上一段音频。``path`` 必填；``start`` 起始帧（默认 0）。"""
    path: str
    start: int = 0
    length_frames: int = 0                    # 0 = 由后续逻辑/模板兜底

    def to_audio_segment(self) -> LTXAudioSegment:
        return LTXAudioSegment(
            audio_path=Path(self.path),
            start_frame=int(self.start),
            length_frames=int(self.length_frames),
        )


class LtxRequest(BaseModel):
    # ----- 提示词 -----
    # global_prompt 优先，兼容旧 prompt
    global_prompt: Optional[str] = None
    prompt: Optional[str] = None              # 旧字段别名
    use_global: Optional[bool] = None         # None → 有提示词即 True

    # ----- 时间轴 -----
    segments: list[SegmentIn] = []
    first_frame: Optional[str] = None         # 旧：prompt 模式 i2v 首帧
    last_frame: Optional[str] = None          # 旧：prompt 模式 i2v 尾帧

    audio_segments: list[AudioSegmentIn] = []
    use_custom_audio: bool = False

    # ----- 模式 -----
    mode: Literal["director", "hd_director"] = "director"

    # ----- 时长 / 帧率 -----
    duration: Optional[float] = None          # 秒（旧：prompt 模式单段时长）
    frame_rate: Optional[int] = None          # 新契约
    fps: Optional[int] = None                 # 旧字段别名

    # ----- 分辨率 -----
    resolution: Optional[str] = None          # 新契约预设串，如 "1280x720"
    aspect: Optional[str] = None              # 旧字段别名
    custom_w: Optional[int] = None
    custom_h: Optional[int] = None
    # 不截断：有首帧图时按图真实像素宽高比出图（默认开）。
    fit_to_input_image: bool = True
    use_custom_resolution: bool = False           # 用户显式指定自定义分辨率(宽/高优先于预设)

    # ----- 采样 -----
    noise_seed: Optional[int] = None
    epsilon: Optional[float] = None

    # ----- 输出 -----
    out_dir: str = "./output"
    filename_prefix: Optional[str] = None     # 新契约
    base_name: Optional[str] = None           # 旧字段别名

    # ----- 轮询 -----
    timeout: float = 1800.0
    poll_interval: float = 8.0

    # ---- 归一化取值 ----
    def eff_frame_rate(self) -> int:
        for v in (self.frame_rate, self.fps):
            if v:
                return int(v)
        return 24

    def eff_global_prompt(self) -> str:
        return (self.global_prompt if self.global_prompt is not None
                else self.prompt) or ""

    def eff_use_global(self) -> bool:
        if self.use_global is not None:
            return bool(self.use_global)
        return bool(self.eff_global_prompt().strip())

    def eff_resolution(self) -> Optional[str]:
        return self.resolution or self.aspect

    def eff_filename_prefix(self) -> str:
        return self.filename_prefix or self.base_name or "spb_video"


def _resolve_workflow_id(cfg, profile_key: str) -> str:
    wf_id = (getattr(cfg, "workflow_ids", None) or {}).get(profile_key) or ""
    if not wf_id and profile_key == "director":
        wf_id = getattr(cfg, "runninghub_workflow_id", "") or ""
    return wf_id


def _build_segments(req: LtxRequest) -> tuple[LTXSegment, ...]:
    """优先用显式 segments；否则用 (global_)prompt + first/last_frame 组 1~2 段。"""
    fr = req.eff_frame_rate()
    if req.segments:
        return tuple(s.to_segment(fr) for s in req.segments)

    prompt = req.eff_global_prompt()
    if not prompt.strip():
        raise ValueError("需提供 global_prompt/prompt 或 segments")
    length = max(1, int(round((req.duration or 1.0) * fr)))
    segs: list[LTXSegment] = [LTXSegment(
        local_prompt=prompt,
        length=length,
        image_path=Path(req.first_frame) if req.first_frame else None,
        segment_type="image" if req.first_frame else "text",
    )]
    if req.last_frame:
        segs.append(LTXSegment(
            local_prompt=prompt,
            length=length,
            image_path=Path(req.last_frame),
            segment_type="image",
        ))
    return tuple(segs)


def _build_audio_segments(req: LtxRequest) -> tuple[LTXAudioSegment, ...]:
    return tuple(a.to_audio_segment() for a in req.audio_segments)


def _do_ltx(req: LtxRequest) -> dict:
    profile_key = _MODE_PROFILE_KEY.get(req.mode)
    if profile_key is None:
        raise ValueError(f"未知 mode: {req.mode}")
    profile = get_profile(profile_key)

    cfg = _load_cfg()
    wf_id = _resolve_workflow_id(cfg, profile.key)
    if not wf_id:
        raise ValueError(
            f"未配置 {profile.name}（{req.mode}）的 workflow_id"
            f"（cfg.workflow_ids['{profile.key}']）")

    segments = _build_segments(req)
    audio_segments = _build_audio_segments(req)

    # 模板：director 尊重 settings 自定义路径（自带兜底）；其它 profile 用内置。
    if profile.key == "director":
        template_path = resolve_template_path(cfg)
    else:
        template_path = template_path_for(profile)

    out_dir = Path(req.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    spec_kwargs: dict = {
        "global_prompt": req.eff_global_prompt(),
        "use_global_prompt": req.eff_use_global(),
        "segments": segments,
        "audio_segments": audio_segments,
        "use_custom_audio": bool(req.use_custom_audio),
        "frame_rate": req.eff_frame_rate(),
        "filename_prefix": req.eff_filename_prefix(),
        "output_dir": out_dir,
        "noise_seed": req.noise_seed,
        "fit_to_input_image": bool(req.fit_to_input_image),
    }
    if req.epsilon is not None:
        spec_kwargs["epsilon"] = float(req.epsilon)

    # 分辨率：自定义宽高优先；否则预设串。
    # 自定义宽高：用户显式设了 use_custom_resolution 或提供了 custom_w/h 即启用
    use_custom = req.use_custom_resolution or (req.custom_w and req.custom_h)
    if use_custom:
        spec_kwargs["use_custom_resolution"] = True
        spec_kwargs["custom_width"] = req.custom_w or 0
        spec_kwargs["custom_height"] = req.custom_h or 0
    else:
        res = req.eff_resolution()
        if res:
            spec_kwargs["resolution_preset"] = res

    spec = LTXDirectorSpec(**spec_kwargs)

    client = _client_factory(cfg)
    builder = LTXTaskBuilder(template_path, profile)
    video_path = _submit(
        client, spec, builder,
        workflow_id=wf_id,
        timeout=float(req.timeout),
        poll_interval=float(req.poll_interval),
    )
    return {"output": str(video_path), "mode": req.mode,
            "workflow_id": wf_id, "profile": profile.key}


@router.post("/ltx")
def ltx(req: LtxRequest):
    """提交一次 LTX 视频生成（director / hd_director）。返回视频文件路径。

    缺 workflow_id / 缺 prompt&segments → 400。
    """
    try:
        return _do_ltx(req)
    except (ValueError, RunningHubInvalidSpec) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (RunningHubUnavailable, RunningHubUploadError,
            RunningHubTaskFailed) as e:
        raise HTTPException(status_code=502, detail=str(e))
