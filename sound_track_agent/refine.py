"""refine_segments: per-shot 多帧情绪 → 邻接聚合 → 替换 session.segments。

供 pipeline.Stages.refine_segments 注入。纯编排，全 I/O 注入。
失败降级返回 False，session 不动，pipeline 据此不置 segments_refined（可续跑重试）。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

from sound_track_agent.session import ScoringSession
from sound_track_agent.shot_detector import detect_shots
from sound_track_agent.segment_planner import cluster_by_emotion
from sound_track_agent.emotion_tagger import tag_emotion_multi
from sound_track_agent.mixdown import extract_frames_at

log = logging.getLogger(__name__)

# 极短 shot 阈值（秒）：duration < 此值时退化为单帧 mid
_MIN_MULTIFRAME_DUR = 0.1


def refine_segments(session: ScoringSession, *, video_path, work_dir,
                    provider, global_style: str,
                    max_segments: int = 5,
                    merge_threshold: float = 0.25,
                    detect: Optional[Callable] = None,
                    extract_frames: Optional[Callable] = None,
                    tag_fn: Optional[Callable] = None) -> bool:
    """1. 重检镜头 2. per-shot 抽 3 帧（极短 shot 退化单帧） 3. 测情绪
       4. 邻接聚合 5. 替换 session.segments。

    返回 True=成功重排（pipeline 据此置 segments_refined）；
    False=失败/跳过（不动 session，pipeline 不置 flag，下次续跑可重试）。

    安全护栏：session 已有任意候选 → 返回 False、不替换。

    所有 I/O 可注入；缺省走真实实现。
    """
    try:
        # 安全护栏：已有候选 → 不动（防止重排打散已生成 BGM）
        if any(getattr(s, "candidates", None) for s in session.segments):
            log.info("refine_segments 跳过：session 已有候选段")
            return False

        detect = detect or detect_shots
        extract_frames = extract_frames or extract_frames_at
        if tag_fn is None:
            tag_fn = lambda paths: tag_emotion_multi(provider, paths, global_style)
        work_dir = Path(work_dir)

        # 1. 重检镜头
        shots = detect(video_path)
        if not shots:
            log.warning("refine_segments: 未检出镜头，保留原 segments")
            return False

        # 2-3. per-shot 抽帧 + 测情绪
        emotions = []
        for i, shot in enumerate(shots):
            mid = (shot.t_start + shot.t_end) / 2.0
            duration = shot.t_end - shot.t_start
            if duration < _MIN_MULTIFRAME_DUR:
                times = [mid]
            else:
                times = [shot.t_start + 0.05, mid, shot.t_end - 0.05]
            shot_dir = work_dir / f"shot{i}"
            frame_paths = extract_frames(video_path, times, shot_dir)
            emotions.append(tag_fn(frame_paths))

        # 4. 邻接聚合
        new_segs = cluster_by_emotion(shots, emotions,
                                      max_segments=max_segments,
                                      merge_threshold=merge_threshold)

        # 5. 替换
        session.segments = new_segs
        return True
    except Exception:
        log.warning("refine_segments 降级，保留原始分段", exc_info=True)
        return False
