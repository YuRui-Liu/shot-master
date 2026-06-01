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
