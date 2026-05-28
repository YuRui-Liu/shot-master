"""把真实功能模块用闭包包成 pipeline.Stages（注入 client/provider/配置）。"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from sound_track_agent.pipeline import Stages
from sound_track_agent.session import SegmentScore, ScoringSession, EmotionTag
from sound_track_agent import emotion_tagger, prompt_composer, music_generator
from sound_track_agent import batch_generator, scorer


def build_stages(*, provider, client, workflow_id: str,
                 work_dir, global_style: str, seeds: list,
                 frame_provider: Callable[[SegmentScore], Path],
                 mix_fn: Optional[Callable[[ScoringSession], str]] = None,
                 align_fn: Optional[Callable[[ScoringSession], None]] = None,
                 max_concurrency: int = 3,
                 score_fn: Optional[Callable] = None,
                 ) -> Stages:
    """组装 Stages：每个回调闭包捕获外部依赖。

    frame_provider(seg)->代表帧路径；mix_fn/align_fn 由调用方注入，
    缺省 align 为 no-op、mix 抛未配置错误。
    """
    work_dir = Path(work_dir)
    seeds = list(seeds)                  # 单次物化：避免下游 generate 闭包再次 list() 时已耗尽（generator 输入）
    seeds_count = len(seeds)
    _score = score_fn or scorer.score_candidate
    cache_dir = work_dir / "cache" / "bgm"

    def compose(seg: SegmentScore):
        return prompt_composer.compose_acestep_inputs(
            global_style, seg.emotion, seg.duration)

    def tag_emotion(seg: SegmentScore, sess: ScoringSession) -> EmotionTag:
        return emotion_tagger.tag_emotion(
            provider, frame_provider(seg), global_style)

    def compose_prompt(seg: SegmentScore, sess: ScoringSession) -> str:
        tags, _bpm, _dur = compose(seg)
        return tags

    def generate(seg: SegmentScore, sess: ScoringSession):
        """逐段回退路径（注入 fake stages 时走）。固定 seeds=参数列表，不读 seg.next_seed——
        真实生产链路走 generate_all（batch_generator），那里才用 seg.next_seed 推进新种子。"""
        tags, bpm, dur = compose(seg)
        seg_dir = work_dir / f"seg{seg.index}"
        return music_generator.generate_bgm(
            client, workflow_id, tags=tags, bpm=bpm, duration=dur,
            out_dir=seg_dir, seeds=list(seeds))

    def generate_all(sess: ScoringSession) -> None:
        batch_generator.generate_all(
            sess, client=client, workflow_id=workflow_id, cache_dir=cache_dir,
            compose=compose, score_fn=_score, seeds_count=seeds_count,
            max_concurrency=max_concurrency)

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
        generate_all=generate_all,
    )
