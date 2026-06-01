"""media_agent LTX 视频端点 — 无 Qt、无网络。

router 尚未挂进 server（由主控 include），故本测试把 router 挂到独立 app 上跑。
monkeypatch _client_factory + _submit（封装 submit_ltx_task→wait_for_result）+
LTXTaskBuilder（避免读真实模板），注入假实现返回假视频路径，断言：
- director / hd_director 两 mode 选对 profile + workflow_id
- 返回结构（output / mode / workflow_id / profile）
- 缺 workflow_id / 缺 prompt&segments → 400
"""
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import media_agent.routes.video as vid_mod


def _make_client():
    app = FastAPI()
    app.include_router(vid_mod.router)
    return TestClient(app)


client = _make_client()


class _FakeCfg:
    """假 cfg：workflow_ids 区分 director / director_v3 两套 workflow_id。"""

    def __init__(self, workflow_ids=None, runninghub_workflow_id=""):
        self.workflow_ids = workflow_ids or {}
        self.runninghub_workflow_id = runninghub_workflow_id
        self.runninghub_api_key = "fake-key"
        self.runninghub_base_url = "https://fake"
        self.runninghub_template_path = ""


class _FakeBuilder:
    """假 LTXTaskBuilder：不读模板、不校验，只记录 profile。"""

    def __init__(self, template_path, profile=None):
        self.template_path = template_path
        self.profile = profile


def _patch(monkeypatch, cfg, captured: dict):
    monkeypatch.setattr(vid_mod, "_load_cfg", lambda: cfg)
    monkeypatch.setattr(vid_mod, "_client_factory",
                        lambda c: object())          # 假 client，不触网
    monkeypatch.setattr(vid_mod, "LTXTaskBuilder", _FakeBuilder)

    def fake_submit(client, spec, builder, *, workflow_id, timeout,
                    poll_interval):
        captured["workflow_id"] = workflow_id
        captured["profile"] = builder.profile.key
        captured["spec"] = spec
        captured["template"] = str(builder.template_path)
        # 返回假视频路径（不轮询、不下载）
        return spec.output_dir / f"{spec.filename_prefix}_FAKE.mp4"

    monkeypatch.setattr(vid_mod, "_submit", fake_submit)


# ---------- director 模式 ----------

def test_ltx_director_mode(tmp_path, monkeypatch):
    cfg = _FakeCfg(workflow_ids={"director": "wf-dir",
                                 "director_v3": "wf-hd"})
    cap: dict = {}
    _patch(monkeypatch, cfg, cap)
    r = client.post("/video/ltx", json={
        "prompt": "a cat walking", "mode": "director",
        "duration": 2.0, "fps": 24, "out_dir": str(tmp_path),
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "director"
    assert body["workflow_id"] == "wf-dir"
    assert body["profile"] == "director"
    assert body["output"].endswith("_FAKE.mp4")
    assert cap["workflow_id"] == "wf-dir"
    assert cap["profile"] == "director"
    # 2s * 24fps = 48 帧的单段
    assert cap["spec"].segments[0].length == 48
    assert "ltx_director_v23" in cap["template"]


# ---------- hd_director 模式 ----------

def test_ltx_hd_director_mode(tmp_path, monkeypatch):
    cfg = _FakeCfg(workflow_ids={"director": "wf-dir",
                                 "director_v3": "wf-hd"})
    cap: dict = {}
    _patch(monkeypatch, cfg, cap)
    r = client.post("/video/ltx", json={
        "prompt": "a dog running", "mode": "hd_director",
        "duration": 1.0, "fps": 30, "out_dir": str(tmp_path),
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "hd_director"
    assert body["workflow_id"] == "wf-hd"          # 选了 director_v3 的 id
    assert body["profile"] == "director_v3"
    assert cap["workflow_id"] == "wf-hd"
    assert cap["profile"] == "director_v3"
    assert "ltx_director_v3_api" in cap["template"]


def test_director_falls_back_to_runninghub_workflow_id(tmp_path, monkeypatch):
    # workflow_ids 无 director；director 模式兜底用 runninghub_workflow_id
    cfg = _FakeCfg(workflow_ids={}, runninghub_workflow_id="legacy-wf")
    cap: dict = {}
    _patch(monkeypatch, cfg, cap)
    r = client.post("/video/ltx", json={
        "prompt": "p", "mode": "director", "duration": 1.0,
        "out_dir": str(tmp_path)})
    assert r.status_code == 200, r.text
    assert r.json()["workflow_id"] == "legacy-wf"


# ---------- explicit segments ----------

def test_ltx_explicit_segments(tmp_path, monkeypatch):
    cfg = _FakeCfg(workflow_ids={"director": "wf-dir"})
    cap: dict = {}
    _patch(monkeypatch, cfg, cap)
    r = client.post("/video/ltx", json={
        "mode": "director", "out_dir": str(tmp_path),
        "segments": [
            {"local_prompt": "scene 1", "length": 30,
             "image_path": "/tmp/a.png"},
            {"local_prompt": "scene 2", "length": 20,
             "segment_type": "text"},
        ],
    })
    assert r.status_code == 200, r.text
    segs = cap["spec"].segments
    assert len(segs) == 2
    assert segs[0].length == 30 and str(segs[0].image_path).endswith("a.png")
    assert segs[1].length == 20 and segs[1].image_path is None


def test_ltx_first_last_frame(tmp_path, monkeypatch):
    cfg = _FakeCfg(workflow_ids={"director": "wf-dir"})
    cap: dict = {}
    _patch(monkeypatch, cfg, cap)
    r = client.post("/video/ltx", json={
        "prompt": "morph", "mode": "director", "duration": 1.0,
        "first_frame": "/tmp/f.png", "last_frame": "/tmp/l.png",
        "out_dir": str(tmp_path)})
    assert r.status_code == 200, r.text
    segs = cap["spec"].segments
    assert len(segs) == 2
    assert str(segs[0].image_path).endswith("f.png")
    assert str(segs[1].image_path).endswith("l.png")


# ---------- 400 cases ----------

def test_ltx_missing_workflow_id_400(tmp_path, monkeypatch):
    cfg = _FakeCfg(workflow_ids={})          # director 无 id，也无 legacy
    cap: dict = {}
    _patch(monkeypatch, cfg, cap)
    r = client.post("/video/ltx", json={
        "prompt": "p", "mode": "director", "duration": 1.0,
        "out_dir": str(tmp_path)})
    assert r.status_code == 400


def test_ltx_hd_missing_workflow_id_400(tmp_path, monkeypatch):
    # 只配了 director；hd_director 没有对应 id → 400（不串用 director 的）
    cfg = _FakeCfg(workflow_ids={"director": "wf-dir"})
    cap: dict = {}
    _patch(monkeypatch, cfg, cap)
    r = client.post("/video/ltx", json={
        "prompt": "p", "mode": "hd_director", "duration": 1.0,
        "out_dir": str(tmp_path)})
    assert r.status_code == 400


def test_ltx_missing_prompt_and_segments_400(tmp_path, monkeypatch):
    cfg = _FakeCfg(workflow_ids={"director": "wf-dir"})
    cap: dict = {}
    _patch(monkeypatch, cfg, cap)
    r = client.post("/video/ltx", json={
        "mode": "director", "out_dir": str(tmp_path)})
    assert r.status_code == 400


# ---------- 完整契约：全字段 ----------

def test_ltx_full_contract_assembly(tmp_path, monkeypatch):
    """全契约字段一次性组装进 LTXDirectorSpec。"""
    cfg = _FakeCfg(workflow_ids={"director": "wf-dir"})
    cap: dict = {}
    _patch(monkeypatch, cfg, cap)
    r = client.post("/video/ltx", json={
        "mode": "director",
        "global_prompt": "cinematic city night",
        "use_global": True,
        "frame_rate": 30,
        "resolution": "1920x1080",
        "noise_seed": 12345,
        "epsilon": 0.7,
        "filename_prefix": "myclip",
        "use_custom_audio": True,
        "out_dir": str(tmp_path),
        "segments": [
            {"prompt": "wide establishing", "duration_frames": 60,
             "ref_image_path": "/tmp/ref.png", "guide": 0.8},
            {"prompt": "close up", "duration_sec": 2.0, "text": True},
        ],
        "audio_segments": [
            {"path": "/tmp/bgm.wav", "start": 0},
            {"path": "/tmp/sfx.wav", "start": 60, "length_frames": 30},
        ],
    })
    assert r.status_code == 200, r.text
    spec = cap["spec"]
    assert spec.global_prompt == "cinematic city night"
    assert spec.use_global_prompt is True
    assert spec.frame_rate == 30
    assert spec.resolution_preset == "1920x1080"
    assert spec.noise_seed == 12345
    assert spec.epsilon == 0.7
    assert spec.filename_prefix == "myclip"
    assert spec.use_custom_audio is True
    # segments
    assert len(spec.segments) == 2
    assert spec.segments[0].length == 60                     # duration_frames
    assert spec.segments[0].guide_strength == 0.8
    assert str(spec.segments[0].image_path).endswith("ref.png")
    assert spec.segments[0].segment_type == "image"
    assert spec.segments[1].length == 60                     # 2.0s * 30fps
    assert spec.segments[1].segment_type == "text"
    assert spec.segments[1].image_path is None
    # audio
    assert len(spec.audio_segments) == 2
    assert str(spec.audio_segments[0].audio_path).endswith("bgm.wav")
    assert spec.audio_segments[1].start_frame == 60
    assert spec.audio_segments[1].length_frames == 30


def test_ltx_duration_sec_to_frames(tmp_path, monkeypatch):
    """段级 duration_sec 按 frame_rate 换算为帧。"""
    cfg = _FakeCfg(workflow_ids={"director": "wf-dir"})
    cap: dict = {}
    _patch(monkeypatch, cfg, cap)
    r = client.post("/video/ltx", json={
        "mode": "director", "frame_rate": 24, "out_dir": str(tmp_path),
        "segments": [{"prompt": "s", "duration_sec": 3.0}],
    })
    assert r.status_code == 200, r.text
    assert cap["spec"].segments[0].length == 72              # 3.0 * 24


def test_ltx_16_9_resolution_into_spec(tmp_path, monkeypatch):
    """16:9 预设串（1280x720）正确组装进 LTXDirectorSpec.resolution_preset，

    且不误置 custom 分辨率（use_custom_resolution 应为 False，宽高保持默认非方形输入）。
    根因排查点：确认 resolution 真的流入 spec，而非中途丢失变方形。
    """
    cfg = _FakeCfg(workflow_ids={"director": "wf-dir"})
    cap: dict = {}
    _patch(monkeypatch, cfg, cap)
    r = client.post("/video/ltx", json={
        "mode": "director", "prompt": "p", "duration": 1.0,
        "resolution": "1280x720", "out_dir": str(tmp_path),
    })
    assert r.status_code == 200, r.text
    spec = cap["spec"]
    assert spec.resolution_preset == "1280x720"
    assert spec.use_custom_resolution is False


def test_ltx_16_9_builds_non_square_nodeinfolist(tmp_path):
    """端到端：16:9 预设经真实 LTXTaskBuilder + 真实 v23 模板 → nodeInfoList 宽高=1280x720。

    回归核心 bug「16:9 变正方形」：模板节点 34 默认 use_custom_resolution=True 且
    custom 宽高近方形；修复后预设须解析为 1280x720 并显式覆盖，断言宽≠高、=16:9。
    """
    from drama_shot_master.providers.runninghub import (
        LTXDirectorSpec, LTXSegment, LTXTaskBuilder, LTXNodes,
        resolve_template_path,
    )
    from drama_shot_master.core.workflow_profiles import get_profile

    template_path = resolve_template_path(_FakeCfg(workflow_ids={}))
    builder = LTXTaskBuilder(template_path, get_profile("director"))
    img = tmp_path / "a.png"
    img.write_bytes(b"x")
    spec = LTXDirectorSpec(
        segments=(LTXSegment(local_prompt="s", length=10, image_path=img),),
        resolution_preset="1280x720 (16:9) (横屏)",
    )
    items = builder.build_node_info_list(spec, {img: "openapi/a.png"})
    res = {it["fieldName"]: it["fieldValue"]
           for it in items if it["nodeId"] == LTXNodes.RESOLUTION}
    assert res.get("custom_width") == 1280
    assert res.get("custom_height") == 720
    # 不是正方形
    assert res["custom_width"] != res["custom_height"]
    # 显式开了 custom 开关，强制覆盖模板默认（否则落回方形）
    assert res.get("use_custom_resolution") is True


def test_ltx_custom_resolution_wh(tmp_path, monkeypatch):
    """custom_w/custom_h → use_custom_resolution + 宽高。"""
    cfg = _FakeCfg(workflow_ids={"director": "wf-dir"})
    cap: dict = {}
    _patch(monkeypatch, cfg, cap)
    r = client.post("/video/ltx", json={
        "mode": "director", "prompt": "p", "duration": 1.0,
        "custom_w": 800, "custom_h": 600, "out_dir": str(tmp_path),
    })
    assert r.status_code == 200, r.text
    spec = cap["spec"]
    assert spec.use_custom_resolution is True
    assert spec.custom_width == 800 and spec.custom_height == 600


def test_ltx_hd_director_full_contract_profile(tmp_path, monkeypatch):
    """hd_director 全契约下仍映射 director_v3 + wf-hd（核心 bug 回归）。"""
    cfg = _FakeCfg(workflow_ids={"director": "wf-dir",
                                 "director_v3": "wf-hd"})
    cap: dict = {}
    _patch(monkeypatch, cfg, cap)
    r = client.post("/video/ltx", json={
        "mode": "hd_director",
        "global_prompt": "hd shot",
        "frame_rate": 24,
        "out_dir": str(tmp_path),
        "segments": [{"prompt": "seg", "duration_frames": 48}],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["profile"] == "director_v3"
    assert body["workflow_id"] == "wf-hd"
    assert cap["profile"] == "director_v3"
    assert "ltx_director_v3_api" in cap["template"]


def test_ltx_use_global_default_from_prompt(tmp_path, monkeypatch):
    """未给 use_global 时由是否有提示词推断。"""
    cfg = _FakeCfg(workflow_ids={"director": "wf-dir"})
    cap: dict = {}
    _patch(monkeypatch, cfg, cap)
    # 有 global_prompt 但只用 segments，use_global 应自动 True
    r = client.post("/video/ltx", json={
        "mode": "director", "global_prompt": "g", "out_dir": str(tmp_path),
        "segments": [{"prompt": "s", "duration_frames": 10}],
    })
    assert r.status_code == 200, r.text
    assert cap["spec"].use_global_prompt is True


def test_ltx_backward_compat_old_fields(tmp_path, monkeypatch):
    """旧窄 body（prompt/fps/aspect/base_name/segments.local_prompt）仍可跑。"""
    cfg = _FakeCfg(workflow_ids={"director": "wf-dir"})
    cap: dict = {}
    _patch(monkeypatch, cfg, cap)
    r = client.post("/video/ltx", json={
        "mode": "director", "fps": 24, "aspect": "1280x720",
        "base_name": "legacy", "out_dir": str(tmp_path),
        "segments": [{"local_prompt": "old", "length": 25,
                      "image_path": "/tmp/o.png"}],
    })
    assert r.status_code == 200, r.text
    spec = cap["spec"]
    assert spec.frame_rate == 24
    assert spec.resolution_preset == "1280x720"
    assert spec.filename_prefix == "legacy"
    assert spec.segments[0].length == 25
    assert spec.segments[0].local_prompt == "old"
    assert str(spec.segments[0].image_path).endswith("o.png")
