"""LTX 视频生成端点：导演台 / 高清导演台。复用 providers.runninghub。

LTX 2.3 支持两种模式（用户强调）：
- mode='director'      → profile key "director"（导演台，节点 4/32/23/34，
                          尊重 settings 自定义模板路径，兜底内置 ltx_director_v23.json）
- mode='hd_director'   → profile key "director_v3"（高清导演台，节点 672/683/654，
                          内置模板 ltx_director_v3_api.json）
两模式各自的 workflow_id 从 cfg.workflow_ids[profile.key] 取；director 还兼容
cfg.runninghub_workflow_id 兜底。profile 由 get_profile(profile.key) 取。

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
    LTXDirectorSpec, LTXSegment, LTXTaskBuilder, submit_ltx_task,
    resolve_template_path,
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
    local_prompt: str
    length: int                              # 帧数
    image_path: Optional[str] = None         # i2v 参考图（None=纯文本段）
    segment_type: Literal["image", "text"] = "image"
    guide_strength: float = 1.0
    seg_id: str = ""

    def to_segment(self) -> LTXSegment:
        return LTXSegment(
            local_prompt=self.local_prompt,
            length=int(self.length),
            image_path=Path(self.image_path) if self.image_path else None,
            segment_type=self.segment_type,
            guide_strength=float(self.guide_strength),
            seg_id=self.seg_id,
        )


class LtxRequest(BaseModel):
    # prompt 或 segments 二选一：给 segments 用其；否则用 prompt 组单段
    prompt: Optional[str] = None
    segments: list[SegmentIn] = []
    first_frame: Optional[str] = None        # i2v 首帧参考图路径（仅 prompt 模式用）
    last_frame: Optional[str] = None         # i2v 尾帧参考图路径（仅 prompt 模式用）
    mode: Literal["director", "hd_director"] = "director"
    duration: Optional[float] = None         # 秒；与 fps 算单段帧数（prompt 模式）
    fps: int = 24
    aspect: Optional[str] = None             # 分辨率预设串，如 "1280x720 (16:9) (横屏)"
    out_dir: str = "./output"
    base_name: str = "spb_video"
    noise_seed: Optional[int] = None
    timeout: float = 1800.0
    poll_interval: float = 8.0


def _resolve_workflow_id(cfg, profile_key: str) -> str:
    wf_id = (getattr(cfg, "workflow_ids", None) or {}).get(profile_key) or ""
    if not wf_id and profile_key == "director":
        wf_id = getattr(cfg, "runninghub_workflow_id", "") or ""
    return wf_id


def _build_segments(req: LtxRequest) -> tuple[LTXSegment, ...]:
    """优先用显式 segments；否则用 prompt + first/last_frame 组 1~2 段。"""
    if req.segments:
        return tuple(s.to_segment() for s in req.segments)
    if not (req.prompt and req.prompt.strip()):
        raise ValueError("需提供 prompt 或 segments")
    length = max(1, int(round((req.duration or 1.0) * req.fps)))
    segs: list[LTXSegment] = [LTXSegment(
        local_prompt=req.prompt,
        length=length,
        image_path=Path(req.first_frame) if req.first_frame else None,
        segment_type="image" if req.first_frame else "text",
    )]
    if req.last_frame:
        segs.append(LTXSegment(
            local_prompt=req.prompt,
            length=length,
            image_path=Path(req.last_frame),
            segment_type="image",
        ))
    return tuple(segs)


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

    # 模板：director 尊重 settings 自定义路径（自带兜底）；其它 profile 用内置。
    if profile.key == "director":
        template_path = resolve_template_path(cfg)
    else:
        template_path = template_path_for(profile)

    out_dir = Path(req.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    spec_kwargs: dict = {
        "global_prompt": req.prompt or "",
        "use_global_prompt": bool(req.prompt),
        "segments": segments,
        "frame_rate": int(req.fps),
        "filename_prefix": req.base_name,
        "output_dir": out_dir,
        "noise_seed": req.noise_seed,
    }
    if req.aspect:
        spec_kwargs["resolution_preset"] = req.aspect
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
