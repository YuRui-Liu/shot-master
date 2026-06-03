"""转场端点：CV 分析(analyze) / ffmpeg 参数干跑(ffmpeg_args) / 渲染(render)。

复用 drama_shot_master.core 的 transition_analyzer + transition_render（零 Qt）。
analyze/ffmpeg_args 用 sync def → FastAPI 自动丢线程池，不阻塞事件循环；
render 跑 ffmpeg（长耗时，同样线程池）。
"""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from drama_shot_master.core.composition_model import CompositionModel
from drama_shot_master.core.transition_analyzer import analyze_composition
from drama_shot_master.core import transition_render as tr

from media_agent.core.sse import sse_event

logger = logging.getLogger(__name__)


def _compute_total_duration(comp: CompositionModel) -> float:
    """根据 composition 计算输出视频总时长（秒）。"""
    kept = comp.kept_clips()
    if not kept:
        return 0.0
    durs = [max(0.01, c.trimmed_duration() or c.duration or 0.0) for c in kept]
    if len(kept) == 1:
        return durs[0]
    total = durs[0]
    for i in range(1, len(kept)):
        t = kept[i - 1].effective_transition()
        d = kept[i - 1].effective_duration()
        if t == "none" or d >= min(durs[i - 1], durs[i]):
            total += durs[i]
        else:
            total += durs[i] - d
    return total

router = APIRouter(prefix="/transition")


class CompositionRequest(BaseModel):
    composition: dict
    project: str = ""  # optional: base directory for resolving relative clip paths


def _resolve_and_validate_clip_paths(
    composition: dict, project: str = ""
) -> tuple[list[str], list[str], list[str]]:
    """Resolve clip paths and validate existence.

    Returns (valid, unresolvable, not_found) — three disjoint lists of raw path strings.
    - ``valid``: absolute (or resolved) paths whose files exist.
    - ``unresolvable``: relative paths with no ``project`` to resolve against — truly
      unusable in any context.
    - ``not_found``: absolute (or resolved) paths whose files do not exist.  Callers
      that can gracefully handle missing files (e.g. CV analysis with neutral scores)
      may treat these as valid; render callers should reject them.
    """
    valid: list[str] = []
    unresolvable: list[str] = []
    not_found: list[str] = []
    for clip in composition.get("clips", []):
        raw = str(clip.get("path", "") or "")
        if not raw:
            unresolvable.append(raw or "<empty>")
            continue
        p = Path(raw)
        if not p.is_absolute():
            if project:
                p = Path(project) / raw
            else:
                logger.warning(
                    "Clip path is relative and no project provided, cannot resolve: %s", raw
                )
                unresolvable.append(raw)
                continue
        if p.exists():
            valid.append(raw)
        else:
            logger.warning("Clip file not found, skipping: %s", p)
            not_found.append(raw)
    return valid, unresolvable, not_found


@router.post("/analyze")
def analyze(req: CompositionRequest):
    """对每个未锁定切口跑 CV，回填 auto_transition/auto_duration/cv_scores。

    先校验所有 clip path 是否存在；缺失的剪除，相对路径必须搭配 project。
    """
    _, unresolvable, not_found = _resolve_and_validate_clip_paths(
        req.composition, req.project)
    if unresolvable:
        logger.warning(
            "analyze: %d clip path(s) unresolvable, cutting from analysis",
            len(unresolvable),
        )
        req.composition["clips"] = [
            c
            for c in req.composition.get("clips", [])
            if str(c.get("path", "")) not in unresolvable
        ]
    if not_found:
        logger.warning(
            "analyze: %d clip path(s) not found, keeping for neutral CV scoring",
            len(not_found),
        )

    comp = CompositionModel.from_dict(req.composition)
    # refine_trim：附带 in/out 网格搜索，回填 auto_in/auto_out 建议（spec §子1）。
    analyze_composition(comp, refine_trim=True)
    return {"composition": comp.to_dict()}


class RenderRequest(BaseModel):
    composition: dict
    out_path: str


class PreviewCutRequest(BaseModel):
    """单切口短样预览：传两片段的 composition + 转场参数，渲一段短片返回路径。"""
    composition: dict          # 仅含切口两侧的 2 个 clip（前端自行筛出）
    out_path: str              # 输出路径（前端传临时路径，如 PROJECT/.cut_preview.mp4）
    preview_window: float = 2.5  # 每侧保留多少秒（截断过长的片段，加速渲染）
    project: str = ""


@router.post("/preview_cut")
def preview_cut(req: PreviewCutRequest):
    """渲染单切口短样片（最多 preview_window×2 秒）。

    前端传切口两侧 2 个 clip 的 composition，本端点把每个片段截断到最多
    preview_window 秒（取末尾/开头），渲染后返回临时文件路径供前端播放。
    文件可重复覆写（out_path 固定为 .cut_preview.mp4），无需清理。
    """
    clips = req.composition.get("clips") or []
    if len(clips) < 2:
        raise HTTPException(status_code=400, detail="composition 需包含恰好 2 个 clip")

    # 截断每个片段，只保留切口附近的 preview_window 秒
    win = max(0.5, req.preview_window)
    clip_a = dict(clips[0])
    clip_b = dict(clips[1])
    dur_a = float(clip_a.get("duration") or 0)
    dur_b = float(clip_b.get("duration") or 0)

    # clip_a：保留末尾 win 秒（in_point 往后推）
    if dur_a > win:
        orig_out_a = float(clip_a.get("out_point") or dur_a)
        clip_a["out_point"] = orig_out_a
        clip_a["in_point"] = max(0.0, orig_out_a - win)

    # clip_b：保留开头 win 秒（out_point 往前推）
    if dur_b > win:
        orig_in_b = float(clip_b.get("in_point") or 0)
        clip_b["in_point"] = orig_in_b
        clip_b["out_point"] = orig_in_b + win

    preview_comp = dict(req.composition)
    preview_comp["clips"] = [clip_a, clip_b]

    valid, unresolvable, not_found = _resolve_and_validate_clip_paths(preview_comp, req.project)
    all_missing = unresolvable + not_found
    if all_missing:
        raise HTTPException(status_code=400,
                            detail=f"片段路径不可用: {', '.join(all_missing)}")

    comp = CompositionModel.from_dict(preview_comp)
    ok, msg = comp.validate()
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    out = tr.render(comp, req.out_path)
    return {"output": out, "warning": (msg if msg != "ok" else "")}


def _probe_from_comp(comp: CompositionModel):
    """用 composition 自带时长做 probe，避免真实探测文件（干跑/测试可用）。"""
    dur = {c.path: (c.trimmed_duration() or c.duration or 0.0) for c in comp.clips}
    return lambda p: dur.get(p, 0.0)


@router.post("/ffmpeg_args")
def ffmpeg_args(req: RenderRequest):
    """干跑：返回将执行的 ffmpeg 参数列表（不实际渲染），便于前端预览/调试。"""
    from drama_shot_master.core.ffmpeg_locate import ffmpeg_path
    comp = CompositionModel.from_dict(req.composition)
    ok, msg = comp.validate()
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    args = tr.build_ffmpeg_args(comp, req.out_path, ffmpeg=ffmpeg_path(),
                                probe=_probe_from_comp(comp))
    return {"args": args, "warning": (msg if msg != "ok" else "")}


@router.post("/render")
def render(req: RenderRequest):
    """实际渲染成片（调用 ffmpeg，长耗时）。"""
    # 校验 clip 路径：无法解析或文件不存在 → 400（渲染需要真文件）
    project = req.composition.get("project", "") if isinstance(req.composition, dict) else ""
    valid, unresolvable, not_found = _resolve_and_validate_clip_paths(req.composition, project)
    all_missing = unresolvable + not_found
    if all_missing:
        raise HTTPException(status_code=400,
                            detail=f"片段路径不可用: {', '.join(all_missing)}")
    # 剔除无效 clip 后再构建模型
    if valid:
        if isinstance(req.composition, dict):
            req.composition["clips"] = [
                c for c in req.composition.get("clips", [])
                if str(c.get("path", "")) in valid
            ]
    comp = CompositionModel.from_dict(req.composition)
    ok, msg = comp.validate()
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    out = tr.render(comp, req.out_path)
    return {"output": out, "warning": (msg if msg != "ok" else "")}


class RenderStreamRequest(BaseModel):
    composition: dict
    out_path: str


@router.post("/render-stream")
async def render_stream(req: RenderStreamRequest):
    """流式渲染成片（SSE），逐帧报告 ffmpeg 进度（基于 stderr time=… 解析）。"""
    # 校验 clip 路径：无法解析或文件不存在 → 400（渲染需要真文件）
    project = req.composition.get("project", "") if isinstance(req.composition, dict) else ""
    valid, unresolvable, not_found = _resolve_and_validate_clip_paths(req.composition, project)
    all_missing = unresolvable + not_found
    if all_missing:
        raise HTTPException(status_code=400,
                            detail=f"片段路径不可用: {', '.join(all_missing)}")
    if valid:
        if isinstance(req.composition, dict):
            req.composition["clips"] = [
                c for c in req.composition.get("clips", [])
                if str(c.get("path", "")) in valid
            ]
    comp = CompositionModel.from_dict(req.composition)
    ok, msg = comp.validate()
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    from drama_shot_master.core.ffmpeg_locate import ffmpeg_path, probe_duration, has_audio_stream

    args = tr.build_ffmpeg_args(
        comp, req.out_path, ffmpeg=ffmpeg_path(),
        probe=probe_duration, has_audio=has_audio_stream,
    )

    total_duration = _compute_total_duration(comp)
    time_re = re.compile(r"time=(\d+):(\d+):(\d+)(?:\.(\d+))?")

    async def gen():
        yield sse_event("status", {"phase": "start", "args": args})

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            yield sse_event("error", {"message": "ffmpeg 可执行文件未找到"})
            return

        last_pct = -1
        while True:
            line_bytes = await proc.stderr.readline()
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8", "ignore")
            m = time_re.search(line)
            if m:
                h, mi, s = int(m[1]), int(m[2]), int(m[3])
                ms = int(m[4]) / 100.0 if m[4] else 0.0
                elapsed = h * 3600 + mi * 60 + s + ms
                pct = round(min(elapsed / total_duration * 100, 100), 1) if total_duration > 0 else 0
                if pct > last_pct:
                    last_pct = pct
                    yield sse_event("progress", {"percent": pct, "elapsed": round(elapsed, 2), "total": round(total_duration, 2)})

        await proc.wait()

        if proc.returncode == 0:
            yield sse_event("done", {"output": req.out_path, "warning": (msg if msg != "ok" else "")})
        else:
            # drain remaining stderr for error tail
            stderr_text = ""
            while True:
                chunk = await proc.stderr.read()
                if not chunk:
                    break
                stderr_text += chunk.decode("utf-8", "ignore")
            tail = (stderr_text)[-800:]
            yield sse_event("error", {"exit_code": proc.returncode, "message": f"ffmpeg 渲染失败：\n{tail}"})

    return StreamingResponse(gen(), media_type="text/event-stream")
