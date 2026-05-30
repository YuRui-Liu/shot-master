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
                    dialogue_segments=None,
                    detect: Callable = detect_shots) -> ScoringSession:
    """MP4 → 切镜头 → 段落聚合 → 新建 ScoringSession。

    dialogue_segments 非 None 时落入 session.dialogue_segments（与 accent_points 同样持久化）。
    """
    mp4 = Path(mp4)
    shots = detect(mp4)
    segments = plan_segments(shots)
    return ScoringSession(
        source_mp4=str(mp4),
        source_hash=hash_file(mp4),
        global_style=style,
        frame_rate=_read_fps(mp4),
        segments=segments,
        dialogue_segments=list(dialogue_segments or []),
    )


def _build_real_stages(cfg, workflow_id, work_dir, global_style,
                       seeds_count, video_path,
                       sfx_session=None) -> Stages:
    """组装真实 Stages（豆包 provider + RunningHub client + mixdown）。

    facade 唯一碰宿主依赖处，仍只读 cfg 属性、不在模块顶层 import 宿主。
    sfx_session 非 None 时，mix_fn 的 partial 会携带 sfx_session 参数，
    使最终 mp4 同时包含 BGM + SFX 层。
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
    from sound_track_agent import scorer
    weights = getattr(cfg, "soundtrack_score_weights", None)
    score_fn = (None if not weights else
                (lambda p, expected_dur=0.0:
                 scorer.score_candidate(p, expected_dur=expected_dur, weights=weights)))
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
                       snap_window=float(getattr(cfg, "accent_snap_window", 0.6)),
                       max_stretch=float(getattr(cfg, "accent_max_stretch", 0.10)),
                       sfx_session=sfx_session,
                       sfx_ducking_db=float(getattr(cfg, "sfx_ducking_db", -6.0))),
        max_concurrency=int(getattr(cfg, "soundtrack_max_concurrency", 3)),
        score_fn=score_fn,
        video_path=video_path,
        refine_max_segments=int(getattr(cfg, "refine_max_segments", 5)),
        refine_merge_threshold=float(getattr(cfg, "refine_merge_threshold", 0.25)),
        refine_frames_per_shot=int(getattr(cfg, "refine_frames_per_shot", 3)),
        fade_out=bool(getattr(cfg, "soundtrack_fade_out", False)),
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
        generate_all=(wrap_whole(stages.generate_all, "批量生成 BGM")
                      if stages.generate_all is not None else None),
        refine_segments=(wrap_whole(stages.refine_segments, "精排段落")
                         if stages.refine_segments is not None else None),
    )


def advance(session: ScoringSession, work_dir, *, cfg, workflow_id: str,
            seeds_count: int = 2, stop_after: str = "mix",
            on_progress: Optional[Callable[[str], None]] = None,
            stages: Optional[Stages] = None,
            dialogue_segments=None,
            sfx_session=None) -> ScoringSession:
    """从 session 当前状态推进到 stop_after（可重复调用=续跑）。

    stages 可注入（测试用 fake）；dialogue_segments 非空时覆盖 session 字段。
    sfx_session 非 None 时，mix 阶段会在 BGM 轨上叠加 SFX 层。
    """
    if stop_after not in STAGE_ORDER:
        raise ValueError(f"未知 stop_after: {stop_after}")
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    if dialogue_segments:
        session.dialogue_segments = list(dialogue_segments)
    real = stages or _build_real_stages(
        cfg, workflow_id, work_dir, session.global_style,
        seeds_count, session.source_mp4,
        sfx_session=sfx_session)
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
                         snap_window: float = 0.6,
                         max_stretch: float = 0.10) -> str:
    """轻量卡点试听：段切对齐 + BGM 拼接 + align + 泵感,产出一条 BGM wav(不含 demucs/
    ducking/视频混流),供 ③卡点页出片前快速听卡点效果。返回 wav 路径。

    各段用选定候选,未选则用候选0(_chosen_bgm 行为)。enabled 关或无卡点 → 仅拼接。
    预览路径与正片 mix 路径共用 align+pump，试听效果与正片一致。
    """
    from sound_track_agent.mixdown import _chosen_bgm
    from sound_track_agent.bgm_assembler import assemble_bgm
    from sound_track_agent.accent_mixer import clip_targets, apply_pump

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    seg_bgms = [_chosen_bgm(s) for s in session.segments]
    accents = list(getattr(session, "accent_points", []) or [])
    gains = [float(getattr(s, "volume", 1.0)) for s in session.segments]
    out = work_dir / "preview_accent_bgm.wav"

    if bool(getattr(session, "accent_mix_enabled", True)) and accents:
        targets = clip_targets([s.duration for s in session.segments], accents,
                               big_threshold=big_threshold, window=snap_window,
                               min_clip=crossfade)
        raw = assemble_bgm(seg_bgms, work_dir / "_preview_raw.wav",
                           crossfade=crossfade, clip_durations=targets,
                           clip_gains=gains)
        from sound_track_agent.beat_aligner import align_beats_to_accents
        stretched, aligned = align_beats_to_accents(
            raw, accents,
            max_stretch=max_stretch,
            big_threshold=big_threshold,
            out_path=work_dir / "_preview_aligned.wav")
        out = apply_pump(stretched, out, accents,
                         strength=float(getattr(session, "pump_strength", 0.6)),
                         skip_indices=aligned)
    else:
        out = assemble_bgm(seg_bgms, out, crossfade=crossfade, clip_gains=gains)
    return str(out)


def regenerate_segment(session: ScoringSession, seg_index: int, work_dir, *,
                       cfg, workflow_id: str, seeds_count: int = 2,
                       client=None, score_fn=None,
                       on_progress: Optional[Callable[[str], None]] = None,
                       ) -> ScoringSession:
    """对单段重跑 generate（用新种子换候选、清选定），不动其它段。落盘并返回。

    client/score_fn 可注入（测试用 fake）；为 None 时内部组装真实依赖。
    全部 job 失败时恢复重生成前的状态，避免持久化"已生成但无候选"的坏态。
    """
    if not (0 <= seg_index < len(session.segments)):
        raise ValueError(f"seg_index 越界: {seg_index}")
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    from sound_track_agent import batch_generator, scorer
    from sound_track_agent.prompt_composer import compose_acestep_inputs

    if client is None:
        from drama_shot_master.providers.runninghub import RunningHubClient
        client = RunningHubClient(
            getattr(cfg, "runninghub_api_key", ""),
            base_url=getattr(cfg, "runninghub_base_url",
                             "https://www.runninghub.cn"))
    if score_fn is None:
        weights = getattr(cfg, "soundtrack_score_weights", None)
        score_fn = (lambda p, expected_dur=0.0:
                    scorer.score_candidate(p, expected_dur=expected_dur,
                                           weights=weights))

    global_style = session.global_style

    def compose(seg):
        return compose_acestep_inputs(
            global_style, seg.emotion, seg.duration,
            fade_out=bool(getattr(cfg, "soundtrack_fade_out", False)))

    seg = session.segments[seg_index]
    _prev = (list(seg.candidates), seg.chosen_candidate, seg.status)

    batch_generator.generate_one(
        session, seg_index, client=client, workflow_id=workflow_id,
        cache_dir=work_dir / "cache" / "bgm", compose=compose, score_fn=score_fn,
        seeds_count=seeds_count,
        max_concurrency=int(getattr(cfg, "soundtrack_max_concurrency", 3)))

    if not seg.candidates:
        # 全部 job 失败：恢复候选/chosen/status 防止持久化坏态；next_seed 保持已推进
        # （契合 spec "无论成败都推进"，避免连续失败下用同一种子窗口卡住）
        seg.candidates, seg.chosen_candidate, seg.status = _prev

    session.save(work_dir / "session.json")
    return session


def apply_directive_to_prompts(session) -> None:
    """把 session.directive 写入各段 music_prompt（纯模板重算，不联网、不生成）。

    effective_style(seg) = directive.segment_directives.get(seg.index)
                           or directive.global_directive or session.global_style
    不触发 RunningHub；不改 candidates/chosen。
    """
    from sound_track_agent.prompt_composer import compose_music_prompt
    d = getattr(session, "directive", None)
    if d is None:
        return
    if d.global_directive:
        session.global_style = d.global_directive
    for seg in session.segments:
        eff = (d.segment_directives.get(seg.index)
               or d.global_directive
               or session.global_style)
        duration = float(seg.t_end) - float(seg.t_start)
        seg.music_prompt = compose_music_prompt(eff, seg.emotion, duration)
