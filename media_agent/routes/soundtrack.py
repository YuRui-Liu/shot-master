"""配乐端点：prompt 组装(纯函数) / BGM 生成 / 批量 / DAW 管线。复用 sound_track_agent。

设计取舍：
- compose_prompt 走 prompt_composer 的纯函数（compose_music_prompt / compose_acestep_inputs），
  确定性、无网络，最适合可测端点。
- generate_bgm 走 sound_track_agent.music_generator.generate_bgm(client, workflow_id, ...)。
  其"需网络的依赖"是 RunningHub 客户端（非情绪 vision provider），故工厂用模块级
  `_client_factory`（测试 monkeypatch 注入假 client，不打真实网络），配置用 `_load_cfg()`。
  prompt 既可由调用方直接给 tags/bpm/duration，也可只给风格/情绪让本端口内组装。
- batch_generate 走 TaskRunner → SSE（对齐 TaskEvent）。

DAW 路由包装（不重写算法，只把 facade / pipeline / mixdown / accent / sfx / overlay
包成 HTTP 端点）：
- advance：走 facade.advance（持久化续跑的真实编排器）。其重依赖（豆包 provider +
  RunningHub + ffmpeg/demucs/cv2）全藏在 facade._build_real_stages，本路由通过模块级
  `_stages_factory` 注入 pipeline.Stages —— 测试给假 stages 即可零依赖跑全管线。
- mixdown：走 mixdown.assemble_and_mix（numpy/ffmpeg 硬限幅多轨下混）。其全部 I/O 子步
  （assemble_bgm/extract_audio/separate/duck/replace_video）皆为可注入参数，本路由通过
  模块级 `_mixdown_io_factory` 注入假 I/O，测试不触 ffmpeg/demucs。
- accent/detect：走 accent_detector.detect_accents（cv2 光流），模块级 `_accent_detector`
  可注入。accent/mix：走 facade.build_accent_preview（段拼接+对齐+泵感的真实卡点试听链），
  其 align/pump 与正片 mix 同路径。
- sfx/detect：走 sfx.facade.plan_sfx_session（provider 可注入）；sfx/generate：走
  sfx.facade.generate_sfx_all（client 可注入）。
- overlay/*：走 overlay_gen.generate_overlay_clip（client 可注入）+ overlay_session
  的 add/remove/list/save。

WS 播放头：**跳过**。facade / ScoringSession / OverlaySession / pipeline 都无服务端
播放时钟或播放头推送 API —— 播放/走带是纯前端（Web Audio / <audio>.currentTime）职责，
后端只产出音频/会话静态产物。强造 ws://…/soundtrack/ws 会凭空发明后端不存在的状态机，
违反"不重写算法"约束，故不建 WS 端点。
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


# ---------- work_dir 校验辅助 ----------

def _validate_work_dir(work_dir: str) -> None:
    """校验 work_dir 存在且可写；否则 raise HTTPException(400)。"""
    p = Path(work_dir)
    if not p.exists():
        raise HTTPException(status_code=400, detail=f"work_dir 不存在: {work_dir}")
    if not p.is_dir():
        raise HTTPException(status_code=400, detail=f"work_dir 不是目录: {work_dir}")
    # 可写性探针（不依赖 os.access，跨平台可靠）
    probe = p / ".writable_test_tmp"
    try:
        probe.touch()
        probe.unlink()
    except (OSError, PermissionError) as e:
        raise HTTPException(
            status_code=400,
            detail=f"work_dir 不可写: {work_dir} ({e})")


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


# ---------- 1b) analyze_segment：对 [start,end] 区间抽帧 → vision 情绪分析 ----------
#
# 复用 sound_track_agent 现有多帧情绪标注（emotion_tagger.tag_emotion_multi）与
# 情绪→ACE-Step tags 组装（prompt_composer.compose_acestep_inputs）。
#
# 两个重依赖各走模块级可注入工厂，测试 monkeypatch 即可零网络/零 ffmpeg：
#   - _vision_provider_factory(cfg)：默认 build_soundtrack_provider（豆包 vision）；
#     provider 须实现 generate(images, system_prompt, user_supplement)。
#   - _frame_extractor(video, times, out_dir)：默认 mixdown.extract_frames_at（ffmpeg），
#     返回与 times 一一对应的帧 png 路径列表。
# global_style 取请求 hint（缺省给一个中性占位串），喂给 vision 情绪 prompt 与 tags 组装。

def _default_vision_provider_factory(cfg):
    from sound_track_agent.provider import build_soundtrack_provider
    return build_soundtrack_provider(cfg)


def _default_frame_extractor(video, times, out_dir):
    from sound_track_agent.mixdown import extract_frames_at
    return extract_frames_at(video, list(times), out_dir)


# 可注入：测试替换为假 vision provider / 假抽帧（不触网、不触 ffmpeg）
_vision_provider_factory = _default_vision_provider_factory
_frame_extractor = _default_frame_extractor


class AnalyzeSegmentRequest(BaseModel):
    video: str
    start_sec: float
    end_sec: float
    hint: Optional[str] = None         # 作品总体风格/情绪提示，喂给 vision 与 tags 组装


@router.post("/analyze_segment")
def analyze_segment(req: AnalyzeSegmentRequest):
    """对 video 的 [start_sec, end_sec] 区间抽 start/mid/end 三帧 → 复用配乐 agent 的多帧
    vision 情绪分析 → 返回 {labels, valence, arousal, intensity, suggested_tags}。

    suggested_tags 复用 prompt_composer.compose_acestep_inputs（Instrumental/dialogue-
    friendly 等）把情绪转 ACE-Step tags 串。vision provider 与抽帧均走模块级可注入工厂。
    """
    from sound_track_agent.emotion_tagger import tag_emotion_multi

    start = float(req.start_sec)
    end = float(req.end_sec)
    if end <= start:
        raise HTTPException(status_code=400, detail="end_sec 必须大于 start_sec")
    if start < 0:
        raise HTTPException(status_code=400, detail="start_sec 不能为负")

    video_path = Path(req.video)
    if not video_path.is_file():
        raise HTTPException(status_code=400, detail=f"视频文件不存在: {req.video}")

    style = (req.hint or "").strip() or "neutral cinematic background"
    duration = end - start
    mid = (start + end) / 2.0
    times = [start, mid, end]

    cfg = _load_cfg()
    import tempfile
    with tempfile.TemporaryDirectory(prefix="analyze_seg_") as td:
        frames = _frame_extractor(req.video, times, td)
        provider = _vision_provider_factory(cfg)
        tag = tag_emotion_multi(provider, list(frames), style)

    suggested_tags, _bpm, _dur = compose_acestep_inputs(style, tag, duration)
    return {
        "labels": list(tag.labels),
        "valence": float(tag.valence),
        "arousal": float(tag.arousal),
        "intensity": float(tag.intensity),
        "suggested_tags": suggested_tags,
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


# ===========================================================================
# DAW 管线路由包装（advance / mixdown / accent / sfx / overlay）
# ===========================================================================
#
# 共用约定：所有"会话"以 work_dir 为锚（facade.load_session / save 都读写
# work_dir/session.json）。重依赖通过模块级工厂注入，测试 monkeypatch 即可。

from sound_track_agent import facade as _facade  # noqa: E402
from sound_track_agent.session import ScoringSession  # noqa: E402


def _session_segment_view(sess: ScoringSession) -> list[dict]:
    """段落精简视图（供前端时间线/状态渲染，避免回传全部候选大字段）。"""
    out = []
    for s in sess.segments:
        chosen = None
        if (s.chosen_candidate is not None
                and 0 <= s.chosen_candidate < len(s.candidates)):
            chosen = s.candidates[s.chosen_candidate].path
        out.append({
            "index": s.index,
            "t_start": s.t_start,
            "t_end": s.t_end,
            "duration": s.duration,
            "status": s.status,
            "music_prompt": s.music_prompt,
            "n_candidates": len(s.candidates),
            "chosen_candidate": s.chosen_candidate,
            "chosen_path": chosen,
            "volume": s.volume,
            "emotion": (s.emotion.to_dict() if s.emotion else None),
        })
    return out


def _accents_view(sess: ScoringSession) -> list[dict]:
    return [{"t": a.t, "intensity": a.intensity, "confirmed": a.confirmed}
            for a in (getattr(sess, "accent_points", []) or [])]


# ---------- advance：推进配乐管线一步（切镜→段落→情绪→生成→对齐→混音） ----------
#
# facade.advance 接受可注入的 stages（pipeline.Stages）；真实依赖在缺省时由
# facade._build_real_stages 组装（豆包 + RunningHub + mixdown）。本路由的可注入点
# 就是这个 stages 工厂：测试给假 stages，生产给 None（=facade 自建真实 stages）。

def _default_stages_factory(session: ScoringSession, work_dir, cfg,
                            workflow_id: str, seeds_count: int):
    """缺省返回 None → facade.advance 内部用 _build_real_stages 组装真实链路。"""
    return None


# 可注入：测试替换为返回假 pipeline.Stages 的工厂（零网络/零 ffmpeg/零 cv2）
_stages_factory = _default_stages_factory


class AdvanceRequest(BaseModel):
    work_dir: str
    # video + global_style 用于在 session.json 不存在时新建会话（首次进入管线）
    video: Optional[str] = None
    global_style: Optional[str] = None
    workflow_id: str = ""
    seeds_count: int = 2
    stop_after: str = "mix"             # STAGE_ORDER 之一
    dialogue_segments: Optional[list[dict]] = None


def _load_or_prepare_session(req: AdvanceRequest) -> ScoringSession:
    sess = _facade.load_session(req.work_dir)
    if sess is not None:
        return sess
    if not (req.video and req.global_style is not None):
        raise ValueError(
            "work_dir 下无 session.json，需提供 video + global_style 以新建会话")
    return _facade.prepare_session(req.video, req.global_style, req.work_dir)


@router.post("/advance")
def advance(req: AdvanceRequest):
    """推进配乐管线到 stop_after 阶段（可重复调用=续跑）。同步 JSON 返回当前会话状态。

    选 JSON 而非 SSE：facade.advance 是"推进到某阶段后整体返回"的阻塞编排器，
    阶段级进度只经 on_progress 回调（无产物），与 TaskRunner 的逐项 SSE 模型不契合。
    前端要分步推进可逐阶段多次调用本端点（refine→tag→prompt→generate→align→mix）。
    """
    _validate_work_dir(req.work_dir)
    try:
        sess = _load_or_prepare_session(req)
        dialogue = None
        if req.dialogue_segments:
            from sound_track_agent.session import DialogueSegment
            dialogue = [DialogueSegment.from_dict(d)
                        for d in req.dialogue_segments]
        cfg = _load_cfg()
        stages = _stages_factory(
            sess, req.work_dir, cfg, req.workflow_id, req.seeds_count)
        sess = _facade.advance(
            sess, req.work_dir, cfg=cfg, workflow_id=req.workflow_id,
            seeds_count=req.seeds_count, stop_after=req.stop_after,
            stages=stages, dialogue_segments=dialogue)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {
        "stop_after": req.stop_after,
        "output": sess.output,
        "segments": _session_segment_view(sess),
        "accents": _accents_view(sess),
        "global_style": sess.global_style,
    }


# ---------- mixdown：真实多轨下混（numpy 硬限幅，走 mixdown.assemble_and_mix） ----------

def _default_mixdown_io_factory() -> dict:
    """缺省返回空 dict → assemble_and_mix 用其模块级真实 I/O（ffmpeg/demucs/soundfile）。"""
    return {}


# 可注入：测试返回 {separate, assemble_bgm_fn, extract_audio_fn, duck_and_mix_fn,
#               replace_video_audio_fn, align_beats, apply_pump_fn, duration_of, ...}
# 全为假实现 → 不触 ffmpeg/demucs。
_mixdown_io_factory = _default_mixdown_io_factory


class MixdownRequest(BaseModel):
    work_dir: str
    crossfade: float = 0.5
    target_lufs: float = -14.0
    big_threshold: float = 0.7
    snap_window: float = 0.6
    max_stretch: float = 0.10


@router.post("/mixdown")
def mixdown(req: MixdownRequest):
    """段 BGM 拼接 → 卡点对齐+泵感 → 对白轨/Demucs → ducking → 写回视频。返回成片路径。

    会话从 work_dir/session.json 读取（须已推进到至少 generate，各段有候选）。
    """
    from sound_track_agent.mixdown import assemble_and_mix
    _validate_work_dir(req.work_dir)
    sess = _facade.load_session(req.work_dir)
    if sess is None:
        raise HTTPException(status_code=400,
                            detail="work_dir 下无 session.json")
    io = _mixdown_io_factory()
    try:
        out = assemble_and_mix(
            sess, sess.source_mp4, req.work_dir,
            crossfade=req.crossfade, target_lufs=req.target_lufs,
            big_threshold=req.big_threshold, snap_window=req.snap_window,
            max_stretch=req.max_stretch, **io)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e))
    sess.output = out
    sess.save(Path(req.work_dir) / "session.json")
    return {"output": out}


# ---------- accent：卡点检测（光流）/ 卡点混音(泵感试听) ----------

def _default_accent_detector(video_path, **kw):
    from sound_track_agent.accent_detector import detect_accents
    return detect_accents(video_path, **kw)


# 可注入：测试返回假 AccentPoint 列表（不触 cv2）
_accent_detector = _default_accent_detector


class AccentDetectRequest(BaseModel):
    video: str
    work_dir: Optional[str] = None     # 给则把检测结果写回 session.accent_points
    k: float = 0.6
    min_gap_s: float = 0.3


@router.post("/accent/detect")
def accent_detect(req: AccentDetectRequest):
    """成片 MP4 → 动作爆点（accent_detector 光流）。给 work_dir 则写回 session 持久化。"""
    pts = _accent_detector(req.video, k=req.k, min_gap_s=req.min_gap_s)
    view = [{"t": float(p.t), "intensity": float(p.intensity),
             "confirmed": bool(getattr(p, "confirmed", False))} for p in pts]
    if req.work_dir:
        _validate_work_dir(req.work_dir)
        sess = _facade.load_session(req.work_dir)
        if sess is not None:
            sess.accent_points = list(pts)
            sess.save(Path(req.work_dir) / "session.json")
    return {"accents": view}


class AccentMixRequest(BaseModel):
    work_dir: str
    crossfade: float = 0.5
    big_threshold: float = 0.7
    snap_window: float = 0.6
    max_stretch: float = 0.10


@router.post("/accent/mix")
def accent_mix(req: AccentMixRequest):
    """卡点混音/泵感试听：段拼接+对齐+泵感产出一条 BGM wav（走 facade.build_accent_preview，
    与正片 mix 共用 align+pump 路径）。返回 wav 路径。"""
    _validate_work_dir(req.work_dir)
    sess = _facade.load_session(req.work_dir)
    if sess is None:
        raise HTTPException(status_code=400,
                            detail="work_dir 下无 session.json")
    try:
        out = _facade.build_accent_preview(
            sess, req.work_dir, crossfade=req.crossfade,
            big_threshold=req.big_threshold, snap_window=req.snap_window,
            max_stretch=req.max_stretch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"preview": out}


# ---------- sfx：检测(规划) / 生成 ----------

def _default_sfx_provider_factory(cfg):
    return None        # None → sfx.facade 内部用 _build_provider 组装真实 provider


def _default_sfx_client_factory(cfg):
    return None        # None → sfx.facade 内部用 _build_client 组装真实 client


# 可注入：测试返回假 provider / 假 client
_sfx_provider_factory = _default_sfx_provider_factory
_sfx_client_factory = _default_sfx_client_factory


def _sfx_session_view(sess) -> dict:
    shots = []
    for s in sess.shots:
        chosen = None
        if (s.chosen_candidate is not None
                and 0 <= s.chosen_candidate < len(s.candidates)):
            chosen = s.candidates[s.chosen_candidate].path
        shots.append({
            "shot_index": s.shot_index,
            "t_start": s.t_start,
            "t_end": s.t_end,
            "duration": s.duration,
            "prompt_short": s.prompt_short,
            "status": s.status,
            "n_candidates": len(s.candidates),
            "chosen_candidate": s.chosen_candidate,
            "chosen_path": chosen,
            "volume": s.volume,
            "enabled": s.enabled,
        })
    return {"source_mp4": sess.source_mp4, "sfx_planned": sess.sfx_planned,
            "shots": shots}


class SfxDetectRequest(BaseModel):
    video: str
    work_dir: str


@router.post("/sfx/detect")
def sfx_detect(req: SfxDetectRequest):
    """检测镜头 + LLM 推荐 SFX prompt → 持久化 sfx_session.json。走 sfx.facade.plan_sfx_session。"""
    from sound_track_agent.sfx import facade as sfx_facade
    _validate_work_dir(req.work_dir)
    cfg = _load_cfg()
    sess = sfx_facade.plan_sfx_session(
        req.video, req.work_dir, cfg=cfg,
        provider=_sfx_provider_factory(cfg))
    return _sfx_session_view(sess)


class SfxGenerateRequest(BaseModel):
    work_dir: str


@router.post("/sfx/generate")
def sfx_generate(req: SfxGenerateRequest):
    """批量生成所有 planned 镜头的 SFX 候选 → 落盘。走 sfx.facade.generate_sfx_all。"""
    from sound_track_agent.sfx import facade as sfx_facade
    _validate_work_dir(req.work_dir)
    sess = sfx_facade.load_sfx_session(req.work_dir)
    if sess is None:
        raise HTTPException(status_code=400,
                            detail="work_dir 下无 sfx_session.json（先调 /sfx/detect）")
    cfg = _load_cfg()
    try:
        sess = sfx_facade.generate_sfx_all(
            sess, req.work_dir, cfg=cfg, client=_sfx_client_factory(cfg))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return _sfx_session_view(sess)


# ---------- overlay：框选生成叠加子轨 ----------

def _default_overlay_client_factory(cfg):
    return None        # None → overlay_gen 内部用 _build_client 组装真实 client


# 可注入：测试返回假 client
_overlay_client_factory = _default_overlay_client_factory


class OverlayGenerateRequest(BaseModel):
    work_dir: str
    kind: str          # "bgm" | "sfx"
    prompt: str
    t_start: float
    t_end: float
    seg_id: Optional[str] = None


@router.post("/overlay/generate")
def overlay_generate(req: OverlayGenerateRequest):
    """框选一个时段 + prompt → 生成 overlay 片段音频 + 自动分轨入 overlay.json。

    走 overlay_gen.generate_overlay_clip（缓存命中复用）+ overlay_session.add/save。
    """
    from sound_track_agent import overlay_gen
    from sound_track_agent.overlay_session import load_overlay, save_overlay
    from secrets import token_hex

    _validate_work_dir(req.work_dir)
    if req.kind not in ("bgm", "sfx"):
        raise HTTPException(status_code=400, detail=f"未知 kind: {req.kind}")
    if req.t_end <= req.t_start:
        raise HTTPException(status_code=400, detail="t_end 必须大于 t_start")
    if not req.prompt or not req.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt 不能为空")
    cfg = _load_cfg()
    duration = float(req.t_end) - float(req.t_start)
    try:
        audio = overlay_gen.generate_overlay_clip(
            req.kind, req.prompt, duration,
            work_dir=req.work_dir, cfg=cfg,
            client=_overlay_client_factory(cfg))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e))

    sess = load_overlay(req.work_dir)
    seg = sess.add(req.kind, req.t_start, req.t_end, req.prompt,
                   seg_id=req.seg_id or token_hex(8), status="generated")
    seg.audio_path = str(audio)
    save_overlay(req.work_dir, sess)
    return {"segment": seg.to_dict()}


class OverlayListRequest(BaseModel):
    work_dir: str


@router.post("/overlay/list")
def overlay_list(req: OverlayListRequest):
    """列出 work_dir/overlay.json 中所有叠加子轨片段。"""
    from sound_track_agent.overlay_session import load_overlay
    _validate_work_dir(req.work_dir)
    sess = load_overlay(req.work_dir)
    return {"segments": [s.to_dict() for s in sess.segments]}


class OverlayRemoveRequest(BaseModel):
    work_dir: str
    seg_id: str


@router.post("/overlay/remove")
def overlay_remove(req: OverlayRemoveRequest):
    """从 overlay.json 删除一个片段。"""
    from sound_track_agent.overlay_session import load_overlay, save_overlay
    _validate_work_dir(req.work_dir)
    sess = load_overlay(req.work_dir)
    removed = sess.remove(req.seg_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"未找到片段: {req.seg_id}")
    save_overlay(req.work_dir, sess)
    return {"removed": req.seg_id,
            "segments": [s.to_dict() for s in sess.segments]}
