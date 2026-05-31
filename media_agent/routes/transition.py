"""转场端点：CV 分析(analyze) / ffmpeg 参数干跑(ffmpeg_args) / 渲染(render)。

复用 drama_shot_master.core 的 transition_analyzer + transition_render（零 Qt）。
analyze/ffmpeg_args 用 sync def → FastAPI 自动丢线程池，不阻塞事件循环；
render 跑 ffmpeg（长耗时，同样线程池）。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from drama_shot_master.core.composition_model import CompositionModel
from drama_shot_master.core.transition_analyzer import analyze_composition
from drama_shot_master.core import transition_render as tr

router = APIRouter(prefix="/transition")


class CompositionRequest(BaseModel):
    composition: dict


@router.post("/analyze")
def analyze(req: CompositionRequest):
    """对每个未锁定切口跑 CV，回填 auto_transition/auto_duration/cv_scores。"""
    comp = CompositionModel.from_dict(req.composition)
    analyze_composition(comp)
    return {"composition": comp.to_dict()}


class RenderRequest(BaseModel):
    composition: dict
    out_path: str


def _probe_from_comp(comp: CompositionModel):
    """用 composition 自带时长做 probe，避免真实探测文件（干跑/测试可用）。"""
    dur = {c.path: (c.trimmed_duration() or c.duration or 0.0) for c in comp.clips}
    return lambda p: dur.get(p, 0.0)


@router.post("/ffmpeg_args")
def ffmpeg_args(req: RenderRequest):
    """干跑：返回将执行的 ffmpeg 参数列表（不实际渲染），便于前端预览/调试。"""
    comp = CompositionModel.from_dict(req.composition)
    ok, msg = comp.validate()
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    args = tr.build_ffmpeg_args(comp, req.out_path, ffmpeg="ffmpeg",
                                probe=_probe_from_comp(comp))
    return {"args": args, "warning": (msg if msg != "ok" else "")}


@router.post("/render")
def render(req: RenderRequest):
    """实际渲染成片（调用 ffmpeg，长耗时）。"""
    comp = CompositionModel.from_dict(req.composition)
    ok, msg = comp.validate()
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    out = tr.render(comp, req.out_path)
    return {"output": out, "warning": (msg if msg != "ok" else "")}
