"""media_agent 资源库 ref_index 端点 — 无 Qt、无网络（tmp 项目目录 + 假 provider）。

覆盖：读空结构 / PUT 整体落盘往返 / 按条 update / 从剧本 extract（注入假 extractor）
/ 单条 generate（注入假 provider 落盘）/ 各类错误码（空/不存在/未知 kind）。
"""
import json

import media_agent.routes.assets as assets_mod
from fastapi.testclient import TestClient

from media_agent.server import create_app
from drama_shot_master.core.compass import paths as _paths

client = TestClient(create_app())


def _make_project(tmp_path):
    """建一个最小项目目录（仅目录存在即可，ref_index 端点按需建子目录）。"""
    pdir = tmp_path / "P-001_demo"
    pdir.mkdir()
    return pdir


# ---------- GET /assets/refs ----------

def test_get_refs_empty_structure(tmp_path):
    pdir = _make_project(tmp_path)
    r = client.get("/assets/refs", params={"project": str(pdir)})
    assert r.status_code == 200, r.text
    body = r.json()
    for kind in ("characters", "scenes", "props"):
        assert body[kind] == {"refs": []}


def test_get_refs_empty_project_400():
    assert client.get("/assets/refs", params={"project": "  "}).status_code == 400


def test_get_refs_missing_project_404():
    r = client.get("/assets/refs", params={"project": "/no/such/dir/xyz"})
    assert r.status_code == 404


# ---------- PUT /assets/refs ----------

def test_put_refs_roundtrip(tmp_path):
    pdir = _make_project(tmp_path)
    payload = {
        "project": str(pdir),
        "refs": {
            "characters": [
                {"name": "女主", "path": "characters/女主_ref.png",
                 "source": "custom", "status": "ready"},
                {"name": "男主", "status": "pending"},
            ],
            "scenes": [{"name": "咖啡馆"}],
        },
    }
    r = client.put("/assets/refs", json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["written"] == {"characters": 2, "scenes": 1}

    # 落盘文件结构对齐 ref_index.json（schema_version + refs）
    cp = _paths.ref_index_path(pdir, "characters")
    on_disk = json.loads(cp.read_text(encoding="utf-8"))
    assert on_disk["schema_version"] == 1
    names = [e["name"] for e in on_disk["refs"]]
    assert names == ["女主", "男主"]

    # GET 回读一致
    got = client.get("/assets/refs", params={"project": str(pdir)}).json()
    assert got["characters"]["refs"][0]["status"] == "ready"
    assert got["scenes"]["refs"][0]["name"] == "咖啡馆"
    # 未写到的 props 仍为空
    assert got["props"] == {"refs": []}


def test_put_refs_unknown_kind_400(tmp_path):
    pdir = _make_project(tmp_path)
    r = client.put("/assets/refs", json={
        "project": str(pdir), "refs": {"weapons": [{"name": "剑"}]}})
    assert r.status_code == 400


# ---------- POST /assets/refs/update ----------

def test_update_ref_creates_then_patches(tmp_path):
    pdir = _make_project(tmp_path)
    # 不存在 → 新建
    r = client.post("/assets/refs/update", json={
        "project": str(pdir), "kind": "props",
        "entity_id": "怀表", "status": "ready", "path": "props/怀表_ref.png"})
    assert r.status_code == 200, r.text
    assert r.json()["entry"] == {
        "name": "怀表", "path": "props/怀表_ref.png",
        "source": "", "status": "ready"}

    # 再次 update：只改 source，path/status 保留
    r2 = client.post("/assets/refs/update", json={
        "project": str(pdir), "kind": "props",
        "entity_id": "怀表", "source": "ai-generated"})
    e = r2.json()["entry"]
    assert e["source"] == "ai-generated"
    assert e["status"] == "ready"
    assert e["path"] == "props/怀表_ref.png"

    # 不重复登记（仍只有一条）
    got = client.get("/assets/refs", params={"project": str(pdir)}).json()
    assert len(got["props"]["refs"]) == 1


def test_update_ref_unknown_kind_400(tmp_path):
    pdir = _make_project(tmp_path)
    r = client.post("/assets/refs/update", json={
        "project": str(pdir), "kind": "nope", "entity_id": "x"})
    assert r.status_code == 400


def test_update_ref_empty_entity_400(tmp_path):
    pdir = _make_project(tmp_path)
    r = client.post("/assets/refs/update", json={
        "project": str(pdir), "kind": "characters", "entity_id": "  "})
    assert r.status_code == 400


# ---------- POST /assets/refs/extract ----------

def test_extract_fills_ref_index(tmp_path, monkeypatch):
    pdir = _make_project(tmp_path)

    fake = {"characters": ["女主", "男主"], "scenes": ["天台"], "props": []}
    monkeypatch.setattr(
        assets_mod.entity_extractor, "extract_entities",
        lambda script_text, **kw: fake)
    # 配置读取不应触网
    monkeypatch.setattr(assets_mod, "_load_cfg", lambda: object())

    r = client.post("/assets/refs/extract", json={
        "project": str(pdir), "script_text": "随便一段剧本"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["added"] == {"characters": 2, "scenes": 1, "props": 0}
    chars = body["refs"]["characters"]["refs"]
    assert [c["name"] for c in chars] == ["女主", "男主"]
    assert all(c["source"] == "ai-generated" and c["status"] == "pending"
               for c in chars)

    # 幂等：重复 extract 同名不新增
    r2 = client.post("/assets/refs/extract", json={
        "project": str(pdir), "script_text": "随便一段剧本"})
    assert r2.json()["added"] == {"characters": 0, "scenes": 0, "props": 0}


def test_extract_empty_when_extractor_returns_empty(tmp_path, monkeypatch):
    pdir = _make_project(tmp_path)
    monkeypatch.setattr(
        assets_mod.entity_extractor, "extract_entities",
        lambda script_text, **kw: {"characters": [], "scenes": [], "props": []})
    monkeypatch.setattr(assets_mod, "_load_cfg", lambda: object())
    r = client.post("/assets/refs/extract", json={"project": str(pdir)})
    assert r.status_code == 200, r.text
    assert r.json()["added"] == {"characters": 0, "scenes": 0, "props": 0}


# ---------- POST /assets/refs/generate ----------

class _FakeProvider:
    def generate(self, prompt, references, *, size, n):
        return [b"FAKE_REF_PNG_%s" % prompt.encode("utf-8")]


def _patch_provider(monkeypatch):
    monkeypatch.setattr(
        assets_mod, "_provider_factory", lambda cfg: _FakeProvider())
    monkeypatch.setattr(assets_mod, "_load_cfg", lambda: object())


def test_generate_ref_saves_and_marks_ready(tmp_path, monkeypatch):
    _patch_provider(monkeypatch)
    pdir = _make_project(tmp_path)

    r = client.post("/assets/refs/generate", json={
        "project": str(pdir), "kind": "characters", "entity_id": "女主"})
    assert r.status_code == 200, r.text
    body = r.json()
    entry = body["entry"]
    assert entry["name"] == "女主"
    assert entry["status"] == "ready"
    assert entry["source"] == "ai-generated"
    assert entry["path"] == "characters/女主_ref.png"

    # 文件真实落盘
    out = pdir / "characters" / "女主_ref.png"
    assert out.exists() and out.read_bytes().startswith(b"FAKE_REF_PNG")

    # ref_index 也已登记 ready
    got = client.get("/assets/refs", params={"project": str(pdir)}).json()
    chars = got["characters"]["refs"]
    assert len(chars) == 1 and chars[0]["status"] == "ready"


def test_generate_ref_provider_failure_500(tmp_path, monkeypatch):
    class _Boom:
        def generate(self, *a, **k):
            raise RuntimeError("no api key")
    monkeypatch.setattr(assets_mod, "_provider_factory", lambda cfg: _Boom())
    monkeypatch.setattr(assets_mod, "_load_cfg", lambda: object())
    pdir = _make_project(tmp_path)
    r = client.post("/assets/refs/generate", json={
        "project": str(pdir), "kind": "props", "entity_id": "怀表"})
    assert r.status_code == 500


def test_generate_ref_unknown_kind_400(tmp_path, monkeypatch):
    _patch_provider(monkeypatch)
    pdir = _make_project(tmp_path)
    r = client.post("/assets/refs/generate", json={
        "project": str(pdir), "kind": "nope", "entity_id": "x"})
    assert r.status_code == 400
