"""media_agent TTS 配音端点 — 无 Qt、无网络。

注入假 RunningHub client（upload/create/query/download 全本地）验证 design/clone
落盘与返回结构 + 空 text 400。

注：tts 路由由主控在 server.py include；本测试自建仅含该 router 的 app，
保证独立可跑（不依赖主控是否已挂载）。
"""
from pathlib import Path

import media_agent.routes.tts as tts_mod
from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()
app.include_router(tts_mod.router)
client = TestClient(app)


class _FakeRHClient:
    """假 RunningHub 客户端：upload/create/query/download 全本地，不触网。"""

    def __init__(self):
        self.created = []
        self.uploaded = []

    def upload_file(self, path):
        self.uploaded.append(Path(path))
        return f"openapi/{Path(path).name}"

    def create_task(self, *, workflow_id, node_info_list=None, **kw):
        self.created.append((workflow_id, node_info_list))
        return "task-xyz"

    def query_task(self, task_id):
        return {"status": "SUCCESS",
                "results": [{"url": "http://fake/voice.flac"}]}

    def download_file(self, url, dest):
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"FAKE_FLAC_BYTES")
        return dest


def _patch(monkeypatch):
    fake = _FakeRHClient()
    monkeypatch.setattr(tts_mod, "_client_factory", lambda cfg: fake)
    monkeypatch.setattr(tts_mod, "_load_cfg", lambda: object())
    return fake


# ---------- design：音色设计落盘 ----------

def test_synthesize_design_saves_flac(tmp_path, monkeypatch):
    fake = _patch(monkeypatch)
    out = tmp_path / "dub"
    r = client.post("/tts/synthesize", json={
        "text": "你好，世界",
        "mode": "design",
        "language": "中文",
        "style": "温柔女声",
        "workflow_id": "wf-design",
        "out_dir": str(out),
        "base_name": "hello",
    })
    assert r.status_code == 200, r.text
    p = Path(r.json()["output"])
    assert p.exists() and p.read_bytes() == b"FAKE_FLAC_BYTES"
    assert p.suffix == ".flac"
    # 用了 design 工作流，未上传任何文件
    assert fake.created[0][0] == "wf-design"
    assert fake.uploaded == []


# ---------- clone：声音克隆，需先上传参考音频 ----------

def test_synthesize_clone_uploads_and_saves(tmp_path, monkeypatch):
    fake = _patch(monkeypatch)
    spk = tmp_path / "spk.wav"
    spk.write_bytes(b"WAV")
    out = tmp_path / "dub_clone"
    r = client.post("/tts/synthesize", json={
        "text": "克隆这段声音",
        "mode": "clone",
        "speaker_file": str(spk),
        "emo_mode": 1,
        "emo_alpha": 0.8,
        "workflow_id": "wf-clone",
        "out_dir": str(out),
        "base_name": "cloned",
    })
    assert r.status_code == 200, r.text
    p = Path(r.json()["output"])
    assert p.exists() and p.read_bytes() == b"FAKE_FLAC_BYTES"
    # 说话人参考音频被上传
    assert spk in fake.uploaded
    assert fake.created[0][0] == "wf-clone"


def test_synthesize_clone_mode3_uploads_emo_audio(tmp_path, monkeypatch):
    fake = _patch(monkeypatch)
    spk = tmp_path / "spk.wav"
    spk.write_bytes(b"WAV")
    emo = tmp_path / "emo.wav"
    emo.write_bytes(b"WAV2")
    out = tmp_path / "dub_m3"
    r = client.post("/tts/synthesize", json={
        "text": "情绪参考",
        "mode": "clone",
        "speaker_file": str(spk),
        "emo_mode": 3,
        "emo_audio_file": str(emo),
        "workflow_id": "wf-clone",
        "out_dir": str(out),
    })
    assert r.status_code == 200, r.text
    assert spk in fake.uploaded and emo in fake.uploaded


# ---------- preview：落临时目录 ----------

def test_preview_returns_output(tmp_path, monkeypatch):
    import base64 as _b64
    _patch(monkeypatch)
    r = client.post("/tts/preview", json={
        "text": "试听一下",
        "mode": "design",
        "style": "旁白",
        "workflow_id": "wf-design",
        "out_dir": "",  # preview 忽略 out_dir，落临时目录
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert "output" in data
    assert "audio_base64" in data
    assert _b64.b64decode(data["audio_base64"]) == b"FAKE_FLAC_BYTES"
    # 临时目录已在 finally 块中清理，不再断言磁盘文件存在


# ---------- 边界：空 text / 缺 workflow_id ----------

def test_synthesize_empty_text_400(tmp_path, monkeypatch):
    _patch(monkeypatch)
    r = client.post("/tts/synthesize", json={
        "text": "   ", "mode": "design", "workflow_id": "wf",
        "out_dir": str(tmp_path)})
    assert r.status_code == 400


def test_synthesize_missing_workflow_400(tmp_path, monkeypatch):
    _patch(monkeypatch)
    # 用空 cfg 且无显式 workflow_id；但 profile 自带默认 workflow_id，
    # 故显式传空串覆盖以触发缺失分支。
    r = client.post("/tts/synthesize", json={
        "text": "有文本",
        "mode": "design",
        "workflow_id": "   ",
        "out_dir": str(tmp_path)})
    assert r.status_code == 400


def test_synthesize_empty_out_dir_400(monkeypatch):
    _patch(monkeypatch)
    r = client.post("/tts/synthesize", json={
        "text": "x", "mode": "design", "workflow_id": "wf", "out_dir": "  "})
    assert r.status_code == 400
