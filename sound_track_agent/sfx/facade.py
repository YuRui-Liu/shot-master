"""SFX 公开 API：与 BGM facade 同结构。

5 个对外入口：
  plan_sfx_session(mp4, work_dir, *, cfg)             → 检测镜头 + LLM 推荐 prompt
  generate_sfx_all(session, work_dir, *, cfg)         → 批量生成候选
  regenerate_sfx_one(session, shot_index, work_dir, *, cfg)  → 单镜重生
  set_sfx_chosen(session, shot_index, cand_index, *, work_dir) → 改选定 + 落盘
  load_sfx_session(work_dir)                          → 反序列化 sfx_session.json
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from sound_track_agent.sfx import batch_generator as sfx_bg
from sound_track_agent.sfx import event_planner
from sound_track_agent.sfx.session import SFXSession, SFXShot


# ---------------------------------------------------------------------------
# 内部 helpers
# ---------------------------------------------------------------------------

def _session_path(work_dir) -> Path:
    return Path(work_dir) / "sfx_session.json"


def _hash_file(path: str) -> str:
    h = hashlib.blake2b(digest_size=8)
    try:
        with open(path, "rb") as f:
            h.update(f.read(65536))
    except OSError:
        return "unknown"
    return h.hexdigest()


def _detect_shots(mp4_path: str, cfg) -> list[dict]:
    """复用 sound_track_agent.shot_detector.detect_shots。

    shot_detector.detect_shots 返回 list[Shot]，其中 Shot 有 index/t_start/t_end，
    但没有 frame_path 字段（frame_path 由 _extract_frames_for_shot 单独提供）。
    这里统一输出固定结构 dict，frame_path 置空字符串。
    """
    from sound_track_agent import shot_detector
    shots = shot_detector.detect_shots(mp4_path)
    return [
        {
            "index": s.index,
            "t_start": float(s.t_start),
            "t_end": float(s.t_end),
            "frame_path": "",           # Shot dataclass 无 frame_path；帧由 _extract_frames_for_shot 提供
        }
        for s in shots
    ]


def _extract_frames_for_shot(mp4_path: str, shot: SFXShot, n: int) -> list[Path]:
    """从镜头时段均匀抽 n 帧，返回 list[Path]。

    使用 mixdown.extract_frames_at：对给定时间列表批量抽帧，比逐帧调
    extract_segment_frame 更直接。帧抽取失败时静默跳过（返回空列表）。
    """
    from sound_track_agent.mixdown import extract_frames_at
    dur = shot.shot_duration
    if dur < 0.5:
        return []
    n = max(1, int(n))
    times = [shot.t_start + dur * (i + 0.5) / n for i in range(n)]
    out_dir = Path(mp4_path).parent / "frames"
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        return extract_frames_at(mp4_path, times, out_dir)
    except Exception:
        return []


def _build_provider(cfg):
    from sound_track_agent.provider import build_soundtrack_provider
    return build_soundtrack_provider(cfg)


def _build_client(cfg):
    from drama_shot_master.providers.runninghub import RunningHubClient
    return RunningHubClient(
        getattr(cfg, "runninghub_api_key", ""),
        base_url=getattr(cfg, "runninghub_base_url", "https://www.runninghub.cn"),
    )


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------

def plan_sfx_session(mp4_path: str, work_dir, *, cfg,
                     provider=None) -> SFXSession:
    """检测镜头切点 + LLM 推荐 SFX prompt → 返回并持久化 SFXSession。

    若 work_dir 下已存在 sfx_session.json 且 source_mp4 一致，则复用已有 session；
    镜头数量变化时清空 shots 重新规划。
    """
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    if provider is None:
        provider = _build_provider(cfg)
    existing = SFXSession.load(_session_path(work_dir))
    raw_shots = _detect_shots(mp4_path, cfg)

    if existing is not None and existing.source_mp4 == mp4_path:
        sess = existing
        if len(sess.shots) != len(raw_shots):
            sess.shots = []
            sess.sfx_planned = False
    else:
        sess = SFXSession(
            source_mp4=mp4_path,
            source_hash=_hash_file(mp4_path),
            frame_rate=float(getattr(cfg, "fps", 24.0) or 24.0),
        )

    if not sess.shots:
        sess.shots = [
            SFXShot(
                shot_index=r["index"],
                t_start=r["t_start"],
                t_end=r["t_end"],
                representative_frame=r["frame_path"],
                duration=max(1.0, min(15.0, r["t_end"] - r["t_start"])),
                volume=float(getattr(cfg, "sfx_default_volume", 0.8)),
            )
            for r in raw_shots
        ]

    frames_per = int(getattr(cfg, "sfx_plan_frames_per_shot", 3))
    event_planner.plan_all(
        sess, provider,
        frames_provider=lambda s, n: _extract_frames_for_shot(mp4_path, s, n),
        frames_per_shot=frames_per,
    )
    sess.save(_session_path(work_dir))
    return sess


def generate_sfx_all(session: SFXSession, work_dir, *, cfg,
                     client=None) -> SFXSession:
    """批量并发生成所有 status=planned 的镜头候选，完成后落盘。"""
    if client is None:
        client = _build_client(cfg)
    cache_dir = Path(work_dir) / "cache" / "sfx"
    sfx_bg.generate_all(
        session,
        client=client,
        workflow_id=str(getattr(cfg, "sfx_workflow_id", "")),
        cache_dir=cache_dir,
        seeds_count=int(getattr(cfg, "sfx_seeds_count", 1)),
        max_concurrency=int(getattr(cfg, "sfx_max_concurrency", 3)),
    )
    session.save(_session_path(work_dir))
    return session


def regenerate_sfx_one(session: SFXSession, shot_index: int, work_dir,
                       *, cfg, client=None) -> SFXSession:
    """单镜重生成：清旧候选 → 生成 → 回填 → 落盘。"""
    if client is None:
        client = _build_client(cfg)
    cache_dir = Path(work_dir) / "cache" / "sfx"
    sfx_bg.generate_one(
        session,
        shot_index,
        client=client,
        workflow_id=str(getattr(cfg, "sfx_workflow_id", "")),
        cache_dir=cache_dir,
        seeds_count=int(getattr(cfg, "sfx_seeds_count", 1)),
        max_concurrency=int(getattr(cfg, "sfx_max_concurrency", 3)),
    )
    session.save(_session_path(work_dir))
    return session


def set_sfx_chosen(session: SFXSession, shot_index: int, cand_index: int,
                   *, work_dir) -> None:
    """更新指定镜头的选定候选索引，并立即落盘。"""
    if not (0 <= shot_index < len(session.shots)):
        raise IndexError(f"shot_index {shot_index} 越界")
    shot = session.shots[shot_index]
    if not (0 <= cand_index < len(shot.candidates)):
        raise IndexError(f"cand_index {cand_index} 越界")
    shot.chosen_candidate = cand_index
    session.save(_session_path(work_dir))


def load_sfx_session(work_dir) -> Optional[SFXSession]:
    """从 work_dir/sfx_session.json 加载 SFXSession；文件不存在或损坏返回 None。"""
    return SFXSession.load(_session_path(work_dir))
