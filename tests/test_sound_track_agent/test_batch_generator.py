import threading

from sound_track_agent import batch_generator, bgm_cache
from sound_track_agent.scorer import CandidateScore
from sound_track_agent.session import ScoringSession, SegmentScore


class FakeClient:
    """记录调用 + 可指定失败 seed + 跟踪并发峰值。"""

    def __init__(self, fail_seeds=()):
        self.fail_seeds = set(fail_seeds)
        self.created = []
        self._lock = threading.Lock()
        self._live = 0
        self.peak = 0
        # task_id -> seed（从 node_info_list 的 NODE_SEED 取）
        self._task_seed = {}

    def create_task(self, *, workflow_id, node_info_list=None):
        seed = next(n["fieldValue"] for n in node_info_list if n["nodeId"] == "109")
        with self._lock:
            self.created.append(seed)
            tid = f"t{len(self.created)}"
            self._task_seed[tid] = seed
            self._live += 1
            self.peak = max(self.peak, self._live)
        return tid

    def query_task(self, task_id):
        seed = self._task_seed[task_id]
        if seed in self.fail_seeds:
            return {"status": "FAILED", "errorMessage": "boom"}
        return {"status": "SUCCESS", "results": [{"url": f"http://x/{seed}.mp3"}]}

    def download_file(self, url, dest):
        from pathlib import Path
        dest = Path(dest); dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"AUDIO-" + url.encode())
        # 模拟下载占时，便于并发峰值观测
        import time
        time.sleep(0.02)
        with self._lock:
            self._live -= 1
        return dest


def _compose(seg):
    # 按段区分 tags，避免不同段（同时长）撞同一 cache_key 而误命中
    return (f"tags{seg.index}", 120, seg.duration)


def _fake_score(path, expected_dur=0.0):
    # 缓存文件名是 hash，不含 seed，故返回常量分即可（pick_best 的 argmax 由 scorer 单测覆盖）
    return CandidateScore(total=0.5, health=1.0, headroom=0.5, beat=0.5)


def _session(n=2):
    segs = [SegmentScore(index=i, t_start=float(i), t_end=float(i) + 1.0,
                         status="prompted") for i in range(n)]
    return ScoringSession(source_mp4="x", source_hash="h", global_style="s",
                          frame_rate=24.0, segments=segs)


def test_generate_all_fills_candidates_scores_chosen_and_advances_seed(tmp_path):
    sess = _session(2)
    client = FakeClient()
    batch_generator.generate_all(
        sess, client=client, workflow_id="wf", cache_dir=tmp_path / "cache",
        compose=_compose, score_fn=_fake_score, seeds_count=2,
        max_concurrency=4, poll_interval=0, sleep=lambda *_: None)
    for seg in sess.segments:
        assert len(seg.candidates) == 2
        assert all(c.score is not None for c in seg.candidates)
        assert all(c.subscores.keys() == {"health", "headroom", "beat"}
                   for c in seg.candidates)
        assert seg.chosen_candidate is not None
        assert seg.next_seed == 3                       # 1 -> +2
    assert sorted(client.created) == [1, 1, 2, 2]       # 两段各 seed 1,2


def test_generate_all_uses_cache_skips_create(tmp_path):
    sess = _session(1)
    cache_dir = tmp_path / "cache"
    # 预置段0 seed1、seed2 的缓存
    for seed in (1, 2):
        key = bgm_cache.cache_key("wf", "tags0", 120, sess.segments[0].duration, seed)
        src = tmp_path / f"pre{seed}.mp3"; src.write_bytes(b"CACHED")
        bgm_cache.store(cache_dir, key, src)
    client = FakeClient()
    batch_generator.generate_all(
        sess, client=client, workflow_id="wf", cache_dir=cache_dir,
        compose=_compose, score_fn=_fake_score, seeds_count=2,
        max_concurrency=4, poll_interval=0, sleep=lambda *_: None)
    assert client.created == []                          # 全命中，零提交
    assert len(sess.segments[0].candidates) == 2


def test_concurrency_cap_respected(tmp_path):
    sess = _session(3)                                   # 3 段 × 2 seed = 6 job
    client = FakeClient()
    batch_generator.generate_all(
        sess, client=client, workflow_id="wf", cache_dir=tmp_path / "cache",
        compose=_compose, score_fn=_fake_score, seeds_count=2,
        max_concurrency=2, poll_interval=0, sleep=lambda *_: None)
    assert client.peak <= 2


def test_failure_isolation_keeps_other_candidates(tmp_path):
    sess = _session(1)
    client = FakeClient(fail_seeds={1})                  # seed1 失败，seed2 成功
    batch_generator.generate_all(
        sess, client=client, workflow_id="wf", cache_dir=tmp_path / "cache",
        compose=_compose, score_fn=_fake_score, seeds_count=2,
        max_concurrency=4, poll_interval=0, sleep=lambda *_: None)
    seg = sess.segments[0]
    assert len(seg.candidates) == 1 and seg.candidates[0].seed == 2
    assert seg.next_seed == 3                            # 仍推进


def test_total_failure_leaves_no_candidates(tmp_path):
    sess = _session(1)
    client = FakeClient(fail_seeds={1, 2})
    batch_generator.generate_all(
        sess, client=client, workflow_id="wf", cache_dir=tmp_path / "cache",
        compose=_compose, score_fn=_fake_score, seeds_count=2,
        max_concurrency=4, poll_interval=0, sleep=lambda *_: None)
    assert sess.segments[0].candidates == []
    assert sess.segments[0].next_seed == 3


def test_generate_one_replaces_with_fresh_seeds(tmp_path):
    sess = _session(1)
    seg = sess.segments[0]
    seg.next_seed = 5
    client = FakeClient()
    batch_generator.generate_one(
        sess, 0, client=client, workflow_id="wf", cache_dir=tmp_path / "cache",
        compose=_compose, score_fn=_fake_score, seeds_count=2,
        max_concurrency=4, poll_interval=0, sleep=lambda *_: None)
    assert sorted(client.created) == [5, 6]              # 用新种子
    assert seg.next_seed == 7
    assert seg.status == "generated"
    assert len(seg.candidates) == 2 and seg.chosen_candidate is not None
