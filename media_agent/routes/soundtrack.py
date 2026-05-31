"""配乐端点：prompt 组装(纯函数) / BGM 生成 / 批量。复用 sound_track_agent。

设计取舍：
- compose_prompt 走 prompt_composer 的纯函数（compose_music_prompt / compose_acestep_inputs），
  确定性、无网络，最适合可测端点。
- generate_bgm 走 sound_track_agent.music_generator.generate_bgm(client, workflow_id, ...)。
  其"需网络的依赖"是 RunningHub 客户端（非情绪 vision provider），故工厂用模块级
  `_client_factory`（测试 monkeypatch 注入假 client，不打真实网络），配置用 `_load_cfg()`。
  prompt 既可由调用方直接给 tags/bpm/duration，也可只给风格/情绪让本端口内组装。
- batch_generate 走 TaskRunner → SSE（对齐 TaskEvent）。
- 跳过：mixdown / 整管线 advance —— 强依赖真实视频(cv2)+音频文件(ffmpeg/demucs)+会话态，
  无法在零依赖 TestClient 下用假数据稳定验证；留给上层 GUI/集成测试。
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from sound_track_agent.prompt_composer import (
    compose_music_prompt, compose_acestep_inputs)
from sound_track_agent.music_generator import generate_bgm
from sound_track_agent.session import EmotionTag
from drama_shot_master.core.task_runner import TaskRunner, TaskItem
from media_agent.core.sse import sse_event

router = APIRouter(prefix="/soundtrack")


def _load_cfg():
    from drama_shot_master.config import load_config
    return load_config()


def _build_bgm_client(cfg):
    """从 cfg 构造 RunningHub 客户端（BGM 文生音乐走它，非情绪 vision provider）。"""
    from drama_shot_master.providers.runninghub import RunningHubClient
    return RunningHubClient(
        getattr(cfg, "runninghub_api_key", ""),
        base_url=getattr(cfg, "runninghub_base_url",
                         "https://www.runninghub.cn"))


# 可注入：测试替换为假 client 工厂（不触网）
_client_factory = _build_bgm_client


class EmotionIn(BaseModel):
    labels: list[str] = []
    valence: float = 0.0
    arousal: float = 0.0
    intensity: float = 0.5

    def to_tag(self) -> EmotionTag:
        return EmotionTag(labels=list(self.labels), valence=self.valence,
                          arousal=self.arousal, intensity=self.intensity)


# ---------- 1) compose_prompt：纯函数、必可测 ----------

class ComposePromptRequest(BaseModel):
    global_style: str
    emotion: Optional[EmotionIn] = None
    duration: float
    fade_out: bool = False


@router.post("/compose_prompt")
def compose_prompt(req: ComposePromptRequest):
    """组装 BGM prompt（人读文本）+ ACE-Step 三元组 (tags,bpm,duration)。纯函数，无网络。"""
    if not req.global_style.strip():
        raise HTTPException(status_code=400, detail="global_style 不能为空")
    emo = req.emotion.to_tag() if req.emotion is not None else None
    music_prompt = compose_music_prompt(req.global_style, emo, req.duration)
    tags, bpm, dur = compose_acestep_inputs(
        req.global_style, emo, req.duration, fade_out=req.fade_out)
    return {
        "music_prompt": music_prompt,
        "acestep": {"tags": tags, "bpm": bpm, "duration": dur},
    }


# ---------- 2) generate_bgm：经可注入 client 工厂生成候选并落盘 ----------

class GenerateBgmRequest(BaseModel):
    workflow_id: str
    out_dir: str
    seeds: list[int] = [1, 2]
    # 直接给 ACE-Step 三元组；缺省则由 global_style/emotion/duration 内部组装
    tags: Optional[str] = None
    bpm: Optional[int] = None
    duration: Optional[float] = None
    global_style: Optional[str] = None
    emotion: Optional[EmotionIn] = None
    fade_out: bool = False
    timeout: float = 600.0
    poll_interval: float = 5.0


def _resolve_acestep(req: GenerateBgmRequest) -> tuple[str, int, float]:
    """取显式三元组；否则用 global_style/emotion/duration 组装。"""
    if req.tags is not None and req.bpm is not None and req.duration is not None:
        return req.tags, int(req.bpm), float(req.duration)
    if not (req.global_style and req.global_style.strip()):
        raise ValueError("需提供 (tags,bpm,duration) 或 (global_style,duration)")
    if req.duration is None:
        raise ValueError("缺少 duration")
    emo = req.emotion.to_tag() if req.emotion is not None else None
    return compose_acestep_inputs(
        req.global_style, emo, req.duration, fade_out=req.fade_out)


def _do_generate_bgm(req: GenerateBgmRequest) -> dict:
    if not req.workflow_id.strip():
        raise ValueError("workflow_id 不能为空")
    if not req.seeds:
        raise ValueError("seeds 不能为空")
    tags, bpm, dur = _resolve_acestep(req)
    client = _client_factory(_load_cfg())
    out_dir = Path(req.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cands = generate_bgm(
        client, req.workflow_id,
        tags=tags, bpm=bpm, duration=dur,
        out_dir=out_dir, seeds=list(req.seeds),
        timeout=req.timeout, poll_interval=req.poll_interval)
    return {
        "acestep": {"tags": tags, "bpm": bpm, "duration": dur},
        "candidates": [c.to_dict() for c in cands],
    }


@router.post("/generate_bgm")
def generate_bgm_route(req: GenerateBgmRequest):
    try:
        return _do_generate_bgm(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------- 3) batch_generate：TaskRunner → SSE ----------

class BatchGenerateRequest(BaseModel):
    items: list[GenerateBgmRequest]


@router.post("/batch_generate")
async def batch_generate(req: BatchGenerateRequest):
    """批量生成 BGM → SSE（对齐 TaskEvent）。单项失败不中断后续。"""
    items = [TaskItem(idx=i, payload={"req": r},
                      base_name=Path(r.out_dir).name)
             for i, r in enumerate(req.items)]

    async def worker(item: TaskItem) -> dict:
        r: GenerateBgmRequest = item.payload["req"]
        return await asyncio.to_thread(_do_generate_bgm, r)

    runner = TaskRunner(items, worker)

    async def gen():
        async for ev in runner.stream():
            yield sse_event(ev.type, ev.payload)

    return StreamingResponse(gen(), media_type="text/event-stream")
