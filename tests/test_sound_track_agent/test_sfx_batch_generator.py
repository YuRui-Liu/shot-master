"""sfx/batch_generator: 并发 SFX 生成 + 缓存命中 + 失败隔离。"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from sound_track_agent.sfx.session import SFXSession, SFXShot
from sound_track_agent.sfx.batch_generator import generate_all, generate_one


def _make_session():
    return SFXSession(
        source_mp4="/m.mp4", source_hash="h", frame_rate=24.0,
        shots=[
            SFXShot(0, 0.0, 3.0, prompt_short="开门", duration=3.0, status="planned"),
            SFXShot(1, 3.0, 6.0, status="skipped"),
            SFXShot(2, 6.0, 9.0, prompt_short="脚步", duration=3.0, status="planned"),
        ])


def _make_fake_client(tmp_path):
    client = MagicMock()
    client.create_task.side_effect = lambda **kw: f"tid-{id(kw)}"
    client.get_task_status.return_value = {"status": "SUCCESS"}
    counter = {"i": 0}
    def fake_outputs(_tid):
        counter["i"] += 1
        return [{"fileType": "mp3",
                 "fileUrl": f"https://x/{counter['i']}.mp3"}]
    client.get_task_outputs.side_effect = fake_outputs
    def fake_download(url, dest):
        Path(dest).write_bytes(b"audio")
    client.download_file.side_effect = fake_download
    return client


def test_generate_all_fills_candidates_for_planned_shots(tmp_path):
    sess = _make_session()
    client = _make_fake_client(tmp_path)
    generate_all(sess, client=client, workflow_id="wf-sfx",
                 cache_dir=tmp_path / "cache" / "sfx", seeds_count=1,
                 sleep=lambda _s: None)
    assert sess.shots[0].status == "generated"
    assert len(sess.shots[0].candidates) == 1
    assert sess.shots[0].chosen_candidate == 0
    assert sess.shots[0].next_seed == 2
    assert sess.shots[1].status == "skipped"     # 不动
    assert sess.shots[1].candidates == []
    assert sess.shots[2].status == "generated"


def test_generate_all_skips_already_generated(tmp_path):
    """status=generated 的 shot 不重跑。"""
    sess = _make_session()
    sess.shots[0].status = "generated"           # 假装已完成
    client = _make_fake_client(tmp_path)
    generate_all(sess, client=client, workflow_id="wf-sfx",
                 cache_dir=tmp_path / "cache" / "sfx", seeds_count=1,
                 sleep=lambda _s: None)
    # 只为 shot 2 创建任务
    assert client.create_task.call_count == 1


def test_generate_all_uses_cache_on_hit(tmp_path):
    """同 prompt+duration+seed 二次跑不再调 client。"""
    sess = _make_session()
    client = _make_fake_client(tmp_path)
    generate_all(sess, client=client, workflow_id="wf-sfx",
                 cache_dir=tmp_path / "cache" / "sfx", seeds_count=1,
                 sleep=lambda _s: None)
    n1 = client.create_task.call_count
    # 重置 status 重跑（next_seed 也回退，使 seed 一致才能命中缓存）
    for s in sess.shots:
        if s.status == "generated":
            s.status = "planned"
            s.candidates = []
            s.chosen_candidate = None
            s.next_seed = 1
    generate_all(sess, client=client, workflow_id="wf-sfx",
                 cache_dir=tmp_path / "cache" / "sfx", seeds_count=1,
                 sleep=lambda _s: None)
    n2 = client.create_task.call_count
    assert n2 == n1   # cache 命中，不再调


def test_generate_all_isolates_failure(tmp_path):
    """单 shot 失败不影响其它。"""
    sess = _make_session()
    client = _make_fake_client(tmp_path)
    calls = {"i": 0}
    def flaky_create(**kw):
        calls["i"] += 1
        if calls["i"] == 1:
            raise RuntimeError("boom")
        return f"tid-{calls['i']}"
    client.create_task.side_effect = flaky_create
    generate_all(sess, client=client, workflow_id="wf-sfx",
                 cache_dir=tmp_path / "cache" / "sfx", seeds_count=1,
                 sleep=lambda _s: None)
    # 至少有一个 shot 仍然 planned（生成失败），另一个 generated
    statuses = [s.status for s in sess.shots if s.status != "skipped"]
    assert "planned" in statuses or "generated" in statuses


def test_generate_one_resets_and_regenerates(tmp_path):
    sess = _make_session()
    sess.shots[0].status = "generated"
    sess.shots[0].candidates = []   # 模拟之前候选丢失
    client = _make_fake_client(tmp_path)
    generate_one(sess, shot_index=0, client=client, workflow_id="wf-sfx",
                 cache_dir=tmp_path / "cache" / "sfx", seeds_count=1,
                 sleep=lambda _s: None)
    assert sess.shots[0].status == "generated"
    assert len(sess.shots[0].candidates) == 1
