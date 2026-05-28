"""配乐管线编排器 + pause/resume。各阶段以可注入函数提供（便于 stub/测试）。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from sound_track_agent.session import (
    ScoringSession, SegmentScore, EmotionTag, BGMCandidate,
)

# 阶段顺序：到达 stop_after 指定阶段后停止（含该阶段）
STAGE_ORDER = ["refine_segments", "tag_emotion", "compose_prompt",
               "generate", "align", "mix"]


@dataclass
class Stages:
    """各阶段实现的注入点。Plan 2-4 用真实实现替换 stub。"""
    tag_emotion: Callable[[SegmentScore, ScoringSession], EmotionTag]
    compose_prompt: Callable[[SegmentScore, ScoringSession], str]
    generate: Callable[[SegmentScore, ScoringSession], list[BGMCandidate]]
    align: Callable[[ScoringSession], None]
    mix: Callable[[ScoringSession], str]
    generate_all: Optional[Callable[[ScoringSession], None]] = None
    refine_segments: Optional[Callable[[ScoringSession], bool]] = None


def _save(sess: ScoringSession, path: Optional[Path]) -> None:
    if path is not None:
        sess.save(path)


def run(sess: ScoringSession,
        stages: Stages,
        session_path: Optional[Path] = None,
        stop_after: str = "mix") -> Optional[str]:
    """按阶段推进 session；到 stop_after 阶段后停止。

    每阶段后落盘，支持中断/续跑（已完成阶段幂等跳过）。
    返回出片路径（若推进到 mix），否则 None。
    """
    if stop_after not in STAGE_ORDER:
        raise ValueError(f"未知 stop_after: {stop_after}")
    limit = STAGE_ORDER.index(stop_after)

    if limit >= STAGE_ORDER.index("refine_segments"):
        if (stages.refine_segments is not None
                and not getattr(sess, "segments_refined", False)):
            ok = stages.refine_segments(sess)
            if ok:
                sess.segments_refined = True
        _save(sess, session_path)
        if limit == STAGE_ORDER.index("refine_segments"):
            return None

    if limit >= STAGE_ORDER.index("tag_emotion"):
        for seg in sess.segments:
            if seg.status == "pending":
                seg.emotion = stages.tag_emotion(seg, sess)
                seg.status = "tagged"
        _save(sess, session_path)
        if limit == STAGE_ORDER.index("tag_emotion"):
            return None

    if limit >= STAGE_ORDER.index("compose_prompt"):
        for seg in sess.segments:
            if seg.status == "tagged":
                seg.music_prompt = stages.compose_prompt(seg, sess)
                seg.status = "prompted"
        _save(sess, session_path)
        if limit == STAGE_ORDER.index("compose_prompt"):
            return None

    if limit >= STAGE_ORDER.index("generate"):
        prompted = [s for s in sess.segments if s.status == "prompted"]
        if stages.generate_all is not None:
            stages.generate_all(sess)
            for seg in prompted:
                if seg.candidates:                 # 0 候选段留 prompted 待续跑
                    seg.status = "generated"
        else:
            for seg in sess.segments:
                if seg.status == "prompted":
                    seg.candidates = stages.generate(seg, sess)
                    seg.status = "generated"
        _save(sess, session_path)
        if limit == STAGE_ORDER.index("generate"):
            return None

    if limit >= STAGE_ORDER.index("align"):
        stages.align(sess)
        for seg in sess.segments:
            if seg.status in ("generated", "chosen"):
                seg.status = "aligned"
        _save(sess, session_path)
        if limit == STAGE_ORDER.index("align"):
            return None

    out = stages.mix(sess)
    sess.output = out
    _save(sess, session_path)
    return out
