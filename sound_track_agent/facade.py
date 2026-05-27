"""配乐 agent 对外门面：GUI 只依赖本模块。

不 import 任何 drama_shot_master；cfg 以鸭子类型读取（getattr）。
"""
from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Callable, Optional

from sound_track_agent.shot_detector import detect_shots
from sound_track_agent.segment_planner import plan_segments
from sound_track_agent.session import ScoringSession, hash_file
from sound_track_agent.pipeline import Stages, run as _pipeline_run, STAGE_ORDER


def _read_fps(video_path) -> float:
    """读视频帧率；读不到返回 24.0。"""
    try:
        import cv2
        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        cap.release()
        return float(fps) if fps and fps > 0 else 24.0
    except Exception:
        return 24.0


def prepare_session(mp4, style: str, work_dir, *,
                    detect: Callable = detect_shots) -> ScoringSession:
    """MP4 → 切镜头 → 段落聚合 → 新建 ScoringSession（快，不调豆包/ACE-Step）。"""
    mp4 = Path(mp4)
    shots = detect(mp4)
    segments = plan_segments(shots)
    return ScoringSession(
        source_mp4=str(mp4),
        source_hash=hash_file(mp4),
        global_style=style,
        frame_rate=_read_fps(mp4),
        segments=segments,
    )


def _build_real_stages(cfg, workflow_id, work_dir, global_style,
                       seeds_count, video_path) -> Stages:
    """组装真实 Stages（豆包 provider + RunningHub client + mixdown）。

    facade 唯一碰宿主依赖处，仍只读 cfg 属性、不在模块顶层 import 宿主。
    """
    from drama_shot_master.providers.runninghub import RunningHubClient
    from sound_track_agent.provider import build_soundtrack_provider
    from sound_track_agent.stages_factory import build_stages
    from sound_track_agent.mixdown import extract_segment_frame, assemble_and_mix

    provider = build_soundtrack_provider(cfg)
    client = RunningHubClient(
        getattr(cfg, "runninghub_api_key", ""),
        base_url=getattr(cfg, "runninghub_base_url",
                         "https://www.runninghub.cn"))
    work_dir = Path(work_dir)
    frames_dir = work_dir / "frames"
    return build_stages(
        provider=provider, client=client, workflow_id=workflow_id,
        work_dir=work_dir, global_style=global_style,
        seeds=list(range(1, seeds_count + 1)),
        frame_provider=lambda seg: extract_segment_frame(
            video_path, seg, frames_dir / f"seg{seg.index}.png"),
        align_fn=_make_align_fn(video_path),
        mix_fn=partial(assemble_and_mix, video_path=video_path,
                       work_dir=work_dir,
                       big_threshold=float(getattr(cfg, "accent_big_threshold", 0.7)),
                       snap_window=float(getattr(cfg, "accent_snap_window", 0.6))),
    )


def _make_align_fn(video_path) -> Callable:
    """align 阶段：光流自动检测爆点填 session.accent_points。

    已有 accent_points（用户编辑过 / 续跑）则不覆盖；检测失败静默跳过（不卡管线）。
    """
    def _align(session: ScoringSession) -> None:
        if session.accent_points:
            return
        try:
            from sound_track_agent.accent_detector import detect_accents
            session.accent_points = detect_accents(video_path)
        except Exception:
            pass
    return _align


def _wrap_progress(stages: Stages, on_progress) -> Stages:
    """包装 stages 的每段回调，调用前用 on_progress 报一句。"""
    if on_progress is None:
        return stages

    def wrap(fn, label):
        def inner(seg, sess):
            on_progress(f"{label} 段 {seg.index}…")
            return fn(seg, sess)
        return inner

    def wrap_whole(fn, label):
        def inner(sess):
            on_progress(f"{label}…")
            return fn(sess)
        return inner

    return Stages(
        tag_emotion=wrap(stages.tag_emotion, "情绪分析"),
        compose_prompt=wrap(stages.compose_prompt, "生成 prompt"),
        generate=wrap(stages.generate, "生成 BGM"),
        align=wrap_whole(stages.align, "对齐卡点"),
        mix=wrap_whole(stages.mix, "混音出片"),
    )


def advance(session: ScoringSession, work_dir, *, cfg, workflow_id: str,
            seeds_count: int = 2, stop_after: str = "mix",
            on_progress: Optional[Callable[[str], None]] = None,
            stages: Optional[Stages] = None) -> ScoringSession:
    """从 session 当前状态推进到 stop_after（可重复调用=续跑）。

    stages 可注入（测试用 fake）；为 None 时内部组装真实 stages。
    """
    if stop_after not in STAGE_ORDER:
        raise ValueError(f"未知 stop_after: {stop_after}")
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    real = stages or _build_real_stages(
        cfg, workflow_id, work_dir, session.global_style,
        seeds_count, session.source_mp4)
    real = _wrap_progress(real, on_progress)
    _pipeline_run(session, real,
                  session_path=work_dir / "session.json",
                  stop_after=stop_after)
    return session


def load_session(work_dir) -> Optional[ScoringSession]:
    """work_dir/session.json 存在则加载，否则 None（供打开任务续跑/缓存）。"""
    p = Path(work_dir) / "session.json"
    if not p.exists():
        return None
    return ScoringSession.load(p)


def set_chosen(session: ScoringSession, seg_index: int, cand_index: int) -> None:
    """写 SegmentScore.chosen_candidate；越界抛 ValueError。"""
    if not (0 <= seg_index < len(session.segments)):
        raise ValueError(f"seg_index 越界: {seg_index}")
    seg = session.segments[seg_index]
    if not (0 <= cand_index < len(seg.candidates)):
        raise ValueError(f"cand_index 越界: {cand_index}")
    seg.chosen_candidate = cand_index


def build_accent_preview(session: ScoringSession, work_dir, *,
                         crossfade: float = 0.5,
                         big_threshold: float = 0.7,
                         snap_window: float = 0.6) -> str:
    """轻量卡点试听：段切对齐 + BGM 拼接 + 泵感,产出一条 BGM wav(不含 demucs/
    ducking/视频混流),供 ③卡点页出片前快速听卡点效果。返回 wav 路径。

    各段用选定候选,未选则用候选0(_chosen_bgm 行为)。enabled 关或无卡点 → 仅拼接。
    """
    from sound_track_agent.mixdown import _chosen_bgm
    from sound_track_agent.bgm_assembler import assemble_bgm
    from sound_track_agent.accent_mixer import clip_targets, apply_pump

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    seg_bgms = [_chosen_bgm(s) for s in session.segments]
    accents = list(getattr(session, "accent_points", []) or [])
    out = work_dir / "preview_accent_bgm.wav"

    if bool(getattr(session, "accent_mix_enabled", True)) and accents:
        targets = clip_targets([s.duration for s in session.segments], accents,
                               big_threshold=big_threshold, window=snap_window,
                               min_clip=crossfade)
        raw = assemble_bgm(seg_bgms, work_dir / "_preview_raw.wav",
                           crossfade=crossfade, clip_durations=targets)
        out = apply_pump(raw, out, accents,
                         strength=float(getattr(session, "pump_strength", 0.6)))
    else:
        out = assemble_bgm(seg_bgms, out, crossfade=crossfade)
    return str(out)


def regenerate_segment(session: ScoringSession, seg_index: int, work_dir, *,
                       cfg, workflow_id: str, seeds_count: int = 2,
                       stages: Optional[Stages] = None) -> ScoringSession:
    """对单段重跑 generate（换候选、清选定），不动其它段。落盘并返回 session。"""
    if not (0 <= seg_index < len(session.segments)):
        raise ValueError(f"seg_index 越界: {seg_index}")
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    real = stages or _build_real_stages(
        cfg, workflow_id, work_dir, session.global_style,
        seeds_count, session.source_mp4)
    seg = session.segments[seg_index]
    seg.candidates = real.generate(seg, session)
    seg.chosen_candidate = None
    seg.status = "generated"
    session.save(work_dir / "session.json")
    return session
