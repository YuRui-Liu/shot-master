"""把真实功能模块用闭包包成 pipeline.Stages（注入 client/provider/配置）。"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from sound_track_agent.pipeline import Stages
from sound_track_agent.session import SegmentScore, ScoringSession, EmotionTag
from sound_track_agent import emotion_tagger, prompt_composer, music_generator


def build_stages(*, provider, client, workflow_id: str,
                 work_dir, global_style: str, seeds: list,
                 frame_provider: Callable[[SegmentScore], Path],
                 mix_fn: Optional[Callable[[ScoringSession], str]] = None,
                 align_fn: Optional[Callable[[ScoringSession], None]] = None
                 ) -> Stages:
    """组装 Stages：每个回调闭包捕获外部依赖。

    frame_provider(seg)->代表帧路径；mix_fn/align_fn 由调用方注入，
    缺省 align 为 no-op、mix 抛未配置错误。
    """
    work_dir = Path(work_dir)

    def tag_emotion(seg: SegmentScore, sess: ScoringSession) -> EmotionTag:
        return emotion_tagger.tag_emotion(
            provider, frame_provider(seg), global_style)

    def compose_prompt(seg: SegmentScore, sess: ScoringSession) -> str:
        tags, _bpm, _dur = prompt_composer.compose_acestep_inputs(
            global_style, seg.emotion, seg.duration)
        return tags

    def generate(seg: SegmentScore, sess: ScoringSession):
        tags, bpm, dur = prompt_composer.compose_acestep_inputs(
            global_style, seg.emotion, seg.duration)
        seg_dir = work_dir / f"seg{seg.index}"
        return music_generator.generate_bgm(
            client, workflow_id, tags=tags, bpm=bpm, duration=dur,
            out_dir=seg_dir, seeds=list(seeds))

    def _noop_align(sess: ScoringSession) -> None:
        return None

    def _unconfigured_mix(sess: ScoringSession) -> str:
        raise RuntimeError("mix_fn 未注入（见 mixdown.assemble_and_mix）")

    return Stages(
        tag_emotion=tag_emotion,
        compose_prompt=compose_prompt,
        generate=generate,
        align=align_fn or _noop_align,
        mix=mix_fn or _unconfigured_mix,
    )
