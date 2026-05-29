"""SFX 批量并发生成 + 缓存 + 失败隔离。

镜像 sound_track_agent.batch_generator 的 BGM 路径，但操作 SFXShot 而非
SegmentScore，缓存用 sfx_cache_key + cache/sfx/ 子目录。
"""
from __future__ import annotations

import time as _time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from sound_track_agent import audio_cache
from sound_track_agent.sfx import generator as sfx_generator
from sound_track_agent.sfx.session import SFXSession, SFXShot, SFXCandidate


@dataclass
class _Job:
    shot_index: int
    seed: int
    prompt: str
    duration: float


def _run_job(job: _Job, *, client, workflow_id: str, cache_dir: Path,
             timeout: float, poll_interval: float, sleep) -> tuple[_Job, Path]:
    """单 job：cache 查询 → miss 则 create+poll+download → store。"""
    key = audio_cache.sfx_cache_key(workflow_id, job.prompt, job.duration, job.seed)
    hit = audio_cache.lookup(cache_dir, key)
    if hit is not None:
        return job, hit
    tmp = Path(cache_dir) / f"_dl_{key}_{id(job)}.mp3"
    sfx_generator.generate_sfx(
        client, workflow_id, prompt=job.prompt, duration=job.duration,
        seed=job.seed, out_path=tmp,
        timeout=timeout, poll_interval=poll_interval, sleep=sleep)
    return job, audio_cache.store(cache_dir, key, tmp)


def _execute(jobs: list[_Job], *, client, workflow_id: str, cache_dir: Path,
             max_concurrency: int, timeout: float, poll_interval: float,
             sleep, on_progress) -> list[tuple[_Job, Path]]:
    """并发跑 jobs，失败隔离。"""
    out: list[tuple[_Job, Path]] = []
    total, done = len(jobs), 0
    if not jobs:
        return out
    with ThreadPoolExecutor(max_workers=max(1, int(max_concurrency))) as ex:
        futs = {ex.submit(_run_job, j, client=client, workflow_id=workflow_id,
                          cache_dir=cache_dir, timeout=timeout,
                          poll_interval=poll_interval, sleep=sleep): j
                for j in jobs}
        for fut in as_completed(futs):
            j = futs[fut]
            done += 1
            try:
                out.append(fut.result())
            except Exception as e:
                if on_progress:
                    on_progress(f"镜 {j.shot_index} seed{j.seed} 生成失败: {e}")
            if on_progress:
                on_progress(f"生成 SFX ({done}/{total})…")
    return out


def _jobs_for_shot(shot: SFXShot, seeds_count: int) -> list[_Job]:
    return [_Job(shot.shot_index, shot.next_seed + k,
                 shot.prompt_short, shot.duration)
            for k in range(seeds_count)]


def generate_all(session: SFXSession, *, client, workflow_id: str,
                 cache_dir, seeds_count: int = 1, max_concurrency: int = 3,
                 timeout: float = 600.0, poll_interval: float = 5.0,
                 sleep: Optional[Callable] = None,
                 on_progress: Optional[Callable[[str], None]] = None) -> None:
    """处理所有 status=planned 的 shot：并发生成 → 缓存 → 回填候选。不抛。"""
    if sleep is None:
        sleep = _time.sleep
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    shots = [s for s in session.shots if s.status == "planned"]
    if not shots:
        return
    jobs = [j for s in shots for j in _jobs_for_shot(s, seeds_count)]
    successes = _execute(jobs, client=client, workflow_id=workflow_id,
                         cache_dir=cache_dir, max_concurrency=max_concurrency,
                         timeout=timeout, poll_interval=poll_interval,
                         sleep=sleep, on_progress=on_progress)
    by_idx: dict[int, list[SFXCandidate]] = {s.shot_index: [] for s in shots}
    for job, path in successes:
        by_idx[job.shot_index].append(SFXCandidate(
            path=str(path), seed=job.seed,
            prompt=f"{job.prompt} Length: {int(job.duration)} seconds"))
    for shot in shots:
        shot.next_seed += seeds_count
        cands = sorted(by_idx[shot.shot_index], key=lambda c: c.seed)
        if not cands:
            continue
        shot.candidates = cands
        shot.chosen_candidate = 0
        shot.status = "generated"


def generate_one(session: SFXSession, shot_index: int, *, client,
                 workflow_id: str, cache_dir, seeds_count: int = 1,
                 max_concurrency: int = 3, timeout: float = 600.0,
                 poll_interval: float = 5.0,
                 sleep: Optional[Callable] = None,
                 on_progress: Optional[Callable[[str], None]] = None) -> SFXSession:
    """单镜重生成：清旧 → 生成 → 回填 → 推进 next_seed。"""
    if sleep is None:
        sleep = _time.sleep
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    if not (0 <= shot_index < len(session.shots)):
        raise IndexError(f"shot_index {shot_index} 越界")
    shot = session.shots[shot_index]
    shot.candidates = []
    shot.chosen_candidate = None
    if not shot.prompt_short:
        return session
    jobs = _jobs_for_shot(shot, seeds_count)
    successes = _execute(jobs, client=client, workflow_id=workflow_id,
                         cache_dir=cache_dir, max_concurrency=max_concurrency,
                         timeout=timeout, poll_interval=poll_interval,
                         sleep=sleep, on_progress=on_progress)
    shot.next_seed += seeds_count
    cands = sorted((SFXCandidate(path=str(p), seed=j.seed,
                                  prompt=f"{j.prompt} Length: {int(j.duration)} seconds")
                    for j, p in successes), key=lambda c: c.seed)
    if cands:
        shot.candidates = cands
        shot.chosen_candidate = 0
        shot.status = "generated"
    return session
