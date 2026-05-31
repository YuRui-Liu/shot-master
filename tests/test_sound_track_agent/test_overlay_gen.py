"""overlay_gen.generate_overlay_clip：框选单片段生成（复用 BGM/SFX 管线 + 缓存）。

测试一律注入假 client / 假缓存，绝不真连网络或 RunningHub。
契约：
  generate_overlay_clip(kind, prompt, duration, *, work_dir, cfg, client=None) -> Path
  - kind == "bgm" → music_generator.generate_bgm(tags=prompt, bpm=默认, duration) 取首结果路径
  - kind == "sfx" → sfx.generator.generate_sfx(prompt, clamp(duration,1,15), seed, out_path)
  - 复用 audio_cache（命中直接返回，未命中生成后入缓存）
  - client 缺省自建 RunningHubClient（本测试始终注入，不触发自建）
  - 生成异常上抛
"""
import pytest

from sound_track_agent import overlay_gen


class _FakeCfg:
    """鸭子类型 cfg：仅暴露 overlay_gen 会读的属性。"""
    soundtrack_workflow_id = "wf-bgm"
    sfx_workflow_id = "wf-sfx"
    runninghub_api_key = "k"
    runninghub_base_url = "https://example.invalid"


class _RealContractClient:
    """模拟真实 RunningHubClient 契约：仅 create_task/query_task/download_file。

    刻意不提供其它方法（避免 MagicMock 掩盖 API 误用）。download_file 写真实字节，
    使返回 Path 可 .exists()。可配置抛错以验证异常上抛。
    """

    def __init__(self, *, raise_on_create=False):
        self.created = []
        self.downloaded = []
        self._raise_on_create = raise_on_create

    def create_task(self, *, workflow_id, node_info_list):
        if self._raise_on_create:
            raise RuntimeError("boom")
        self.created.append((workflow_id, node_info_list))
        return "tid-1"

    def query_task(self, task_id):
        return {"status": "SUCCESS",
                "results": [{"url": "https://x/y.mp3", "outputType": "mp3"}]}

    def download_file(self, url, dest):
        from pathlib import Path
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"audio-bytes")
        self.downloaded.append((url, str(dest)))
        return dest


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """轮询 sleep 置空，测试不真等。"""
    monkeypatch.setattr("sound_track_agent.music_generator.time.sleep",
                        lambda _s: None, raising=False)
    monkeypatch.setattr("sound_track_agent.sfx.generator._time.sleep",
                        lambda _s: None, raising=False)


# ---------------------------------------------------------------------------
# BGM 路径
# ---------------------------------------------------------------------------

def test_bgm_returns_path(tmp_path):
    """kind=bgm → 走 generate_bgm 取首结果 → 返回存在的 Path。"""
    client = _RealContractClient()
    out = overlay_gen.generate_overlay_clip(
        "bgm", "悲伤钢琴", 12.0,
        work_dir=tmp_path, cfg=_FakeCfg(), client=client)
    from pathlib import Path
    assert isinstance(out, Path)
    assert out.exists()
    # tags=prompt 透传到 BGM workflow
    wf, nodes = client.created[0]
    assert wf == "wf-bgm"
    assert any(n.get("fieldValue") == "悲伤钢琴" for n in nodes)


def test_bgm_uses_cache_on_second_call(tmp_path):
    """同 (prompt,duration) 二次调用命中缓存，不再 create_task。"""
    cfg = _FakeCfg()
    c1 = _RealContractClient()
    p1 = overlay_gen.generate_overlay_clip(
        "bgm", "悲伤钢琴", 12.0, work_dir=tmp_path, cfg=cfg, client=c1)
    assert len(c1.created) == 1

    c2 = _RealContractClient()
    p2 = overlay_gen.generate_overlay_clip(
        "bgm", "悲伤钢琴", 12.0, work_dir=tmp_path, cfg=cfg, client=c2)
    assert p2 == p1
    assert c2.created == []      # 缓存命中：未发起新任务


# ---------------------------------------------------------------------------
# SFX 路径
# ---------------------------------------------------------------------------

def test_sfx_returns_path(tmp_path):
    """kind=sfx → 走 generate_sfx → 返回存在的 Path。"""
    client = _RealContractClient()
    out = overlay_gen.generate_overlay_clip(
        "sfx", "门吱呀", 3.0,
        work_dir=tmp_path, cfg=_FakeCfg(), client=client)
    from pathlib import Path
    assert isinstance(out, Path)
    assert out.exists()
    wf, nodes = client.created[0]
    assert wf == "wf-sfx"
    assert any(n.get("fieldValue") == "门吱呀" for n in nodes)


def test_sfx_duration_clamped_low(tmp_path, monkeypatch):
    """SFX 时长 < 1 → clamp 到 1。"""
    seen = {}

    real = overlay_gen.generate_sfx

    def _spy(client, workflow_id, *, prompt, duration, seed, out_path, **kw):
        seen["duration"] = duration
        return real(client, workflow_id, prompt=prompt, duration=duration,
                    seed=seed, out_path=out_path, **kw)

    monkeypatch.setattr(overlay_gen, "generate_sfx", _spy)
    overlay_gen.generate_overlay_clip(
        "sfx", "短音", 0.2, work_dir=tmp_path, cfg=_FakeCfg(),
        client=_RealContractClient())
    assert seen["duration"] == 1.0


def test_sfx_duration_clamped_high(tmp_path, monkeypatch):
    """SFX 时长 > 15 → clamp 到 15。"""
    seen = {}
    real = overlay_gen.generate_sfx

    def _spy(client, workflow_id, *, prompt, duration, seed, out_path, **kw):
        seen["duration"] = duration
        return real(client, workflow_id, prompt=prompt, duration=duration,
                    seed=seed, out_path=out_path, **kw)

    monkeypatch.setattr(overlay_gen, "generate_sfx", _spy)
    overlay_gen.generate_overlay_clip(
        "sfx", "长音", 99.0, work_dir=tmp_path, cfg=_FakeCfg(),
        client=_RealContractClient())
    assert seen["duration"] == 15.0


def test_bgm_duration_not_clamped(tmp_path, monkeypatch):
    """BGM 时长不受 1-15 clamp（直接透传）。"""
    seen = {}
    real = overlay_gen.generate_bgm

    def _spy(client, workflow_id, *, tags, bpm, duration, **kw):
        seen["duration"] = duration
        return real(client, workflow_id, tags=tags, bpm=bpm,
                    duration=duration, **kw)

    monkeypatch.setattr(overlay_gen, "generate_bgm", _spy)
    overlay_gen.generate_overlay_clip(
        "bgm", "长曲", 40.0, work_dir=tmp_path, cfg=_FakeCfg(),
        client=_RealContractClient())
    assert seen["duration"] == 40.0


# ---------------------------------------------------------------------------
# 异常上抛
# ---------------------------------------------------------------------------

def test_generation_error_propagates(tmp_path):
    """生成异常上抛（由 worker 捕获），不被吞。"""
    client = _RealContractClient(raise_on_create=True)
    with pytest.raises(RuntimeError):
        overlay_gen.generate_overlay_clip(
            "sfx", "门吱呀", 3.0, work_dir=tmp_path, cfg=_FakeCfg(),
            client=client)


def test_unknown_kind_raises(tmp_path):
    """未知 kind → ValueError。"""
    with pytest.raises(ValueError):
        overlay_gen.generate_overlay_clip(
            "voice", "x", 3.0, work_dir=tmp_path, cfg=_FakeCfg(),
            client=_RealContractClient())
