"""批量并发生成 BGM：收集 (段,seed) 任务 → 查缓存 → 并发提交/轮询/下载 →
写缓存 → 打分 → 回填候选/chosen → 推进 next_seed。

供 pipeline.Stages.generate_all 注入。纯编排，外部依赖（client/compose/
score_fn/sleep）全部注入，便于单测。失败按 job 隔离、不抛（保住部分进度）。
"""
from __future__ import annotations

import time as _time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from sound_track_agent import bgm_cache, music_generator, scorer
from sound_track_agent.session import ScoringSession, BGMCandidate


@dataclass
class _Job:
    seg_index: int
    seed: int
    tags: str
    bpm: int
    duration: float


def _run_job(job: _Job, *, client, workflow_id, cache_dir,
             timeout, poll_interval, sleep):
    """单 job 完整生命周期：查缓存→(miss)create/poll/download/store。返回 (job, Path)。"""
    key = bgm_cache.cache_key(workflow_id, job.tags, job.bpm, job.duration, job.seed)
    hit = bgm_cache.lookup(cache_dir, key)
    if hit is not None:
        return job, hit
    task_id = client.create_task(
        workflow_id=workflow_id,
        node_info_list=music_generator._node_info(
            job.tags, job.bpm, job.duration, job.seed))
    url = music_generator._wait_success(
        client, task_id, timeout=timeout, poll_interval=poll_interval, sleep=sleep)
    # tmp 名带 id(job) 以避免：若 caller 的 compose 退化为多段同输出 → 多 worker 撞同一 _dl_<key>
    tmp = Path(cache_dir) / f"_dl_{key}_{id(job)}.mp3"
    client.download_file(url, tmp)
    return job, bgm_cache.store(cache_dir, key, tmp)


def _execute(jobs, *, client, workflow_id, cache_dir, max_concurrency,
             timeout, poll_interval, sleep, on_progress):
    """并发跑 jobs，返回成功的 (job, Path) 列表；失败经 on_progress 告警并跳过。"""
    out, total, done = [], len(jobs), 0
    if not jobs:
        return out
    with ThreadPoolExecutor(max_workers=max(1, int(max_concurrency))) as ex:
        futs = {ex.submit(_run_job, j, client=client, workflow_id=workflow_id,
                          cache_dir=cache_dir, timeout=timeout,
                          poll_interval=poll_interval, sleep=sleep): j for j in jobs}
        for fut in as_completed(futs):
            j = futs[fut]
            done += 1
            try:
                out.append(fut.result())
            except Exception as e:                     # 失败隔离
                if on_progress:
                    on_progress(f"段{j.seg_index} seed{j.seed} 生成失败：{e}")
            if on_progress:
                on_progress(f"生成 BGM ({done}/{total})…")
    return out


def _score_and_pick(seg, cands, score_fn) -> None:
    """对候选打分写 score/subscores，pick_best 写 seg.chosen_candidate。"""
    for c in cands:
        try:
            cs = score_fn(c.path, expected_dur=seg.duration)
        except Exception:
            cs = None
        if cs is not None:
            c.score = cs.total
            c.subscores = {"health": cs.health, "headroom": cs.headroom,
                           "beat": cs.beat}
        else:
            c.score = None
    seg.chosen_candidate = scorer.pick_best(cands)


def _jobs_for_segment(seg, compose, seeds_count) -> list[_Job]:
    tags, bpm, dur = compose(seg)
    return [_Job(seg.index, seg.next_seed + k, tags, bpm, dur)
            for k in range(seeds_count)]


def generate_all(session: ScoringSession, *, client, workflow_id: str, cache_dir,
                 compose: Callable, score_fn: Callable,
                 seeds_count: int = 2, max_concurrency: int = 3,
                 timeout: float = 600.0, poll_interval: float = 5.0,
                 sleep: Optional[Callable] = None,
                 on_progress: Optional[Callable[[str], None]] = None) -> None:
    """处理所有 prompted 段：并发生成→缓存→打分→回填→推进 next_seed。不抛。

    注：本函数不修改 seg.status；由 pipeline.run 在返回后统一把"已有候选"的 prompted 段
    升到 generated（0 候选段留 prompted 以便续跑重试）。
    """
    if sleep is None:
        sleep = _time.sleep
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    segs = [s for s in session.segments if s.status == "prompted"]
    if not segs:
        return
    jobs = [j for seg in segs for j in _jobs_for_segment(seg, compose, seeds_count)]
    successes = _execute(jobs, client=client, workflow_id=workflow_id,
                         cache_dir=cache_dir, max_concurrency=max_concurrency,
                         timeout=timeout, poll_interval=poll_interval,
                         sleep=sleep, on_progress=on_progress)
    by_index = {s.index: [] for s in segs}
    for job, path in successes:
        by_index[job.seg_index].append(
            BGMCandidate(path=str(path), seed=job.seed, prompt=job.tags))
    for seg in segs:
        seg.next_seed += seeds_count                   # 无论成败都推进
        cands = sorted(by_index[seg.index], key=lambda c: c.seed)
        if not cands:
            continue                                   # 0 候选留 prompted
        _score_and_pick(seg, cands, score_fn)
        seg.candidates = cands


def generate_one(session: ScoringSession, seg_index: int, *, client,
                 workflow_id: str, cache_dir, compose: Callable, score_fn: Callable,
                 seeds_count: int = 2, max_concurrency: int = 3,
                 timeout: float = 600.0, poll_interval: float = 5.0,
                 sleep: Optional[Callable] = None,
                 on_progress: Optional[Callable[[str], None]] = None) -> ScoringSession:
    """单段重生成：新种子、清旧候选、生成、打分、pick、推进 next_seed。

    seg_index 必须在 session.segments 范围内（调用方负责校验，越界抛 IndexError）。
    """
    if sleep is None:
        sleep = _time.sleep
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    seg = session.segments[seg_index]
    seg.candidates = []
    seg.chosen_candidate = None
    jobs = _jobs_for_segment(seg, compose, seeds_count)
    successes = _execute(jobs, client=client, workflow_id=workflow_id,
                         cache_dir=cache_dir, max_concurrency=max_concurrency,
                         timeout=timeout, poll_interval=poll_interval,
                         sleep=sleep, on_progress=on_progress)
    seg.next_seed += seeds_count
    cands = sorted((BGMCandidate(path=str(p), seed=j.seed, prompt=j.tags)
                    for j, p in successes), key=lambda c: c.seed)
    if cands:
        _score_and_pick(seg, cands, score_fn)
        seg.candidates = cands
        seg.status = "generated"
    return session
