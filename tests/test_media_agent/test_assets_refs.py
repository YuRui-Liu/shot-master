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


# ---------- 角色三视图 prompt 增广（#4） ----------

class _CapturingProvider:
    """记录最后一次传入的 prompt，供断言增广关键词。"""
    last_prompt = ""

    def generate(self, prompt, references, *, size, n):
        type(self).last_prompt = prompt
        return [b"FAKE"]


def _patch_capturing(monkeypatch):
    _CapturingProvider.last_prompt = ""
    monkeypatch.setattr(
        assets_mod, "_provider_factory", lambda cfg: _CapturingProvider())
    monkeypatch.setattr(assets_mod, "_load_cfg", lambda: object())


def test_generate_character_prompt_injects_three_view(tmp_path, monkeypatch):
    """角色类 generate 必须把三视图/无背景约束注入 provider 收到的 prompt。"""
    _patch_capturing(monkeypatch)
    pdir = _make_project(tmp_path)
    r = client.post("/assets/refs/generate", json={
        "project": str(pdir), "kind": "characters",
        "entity_id": "女主", "prompt": "红衣少女"})
    assert r.status_code == 200, r.text
    sent = _CapturingProvider.last_prompt
    # 原始描述保留
    assert "红衣少女" in sent
    # 三视图关键词
    assert "three-view" in sent
    assert "front side back" in sent
    # 无场景背景约束
    assert "no scene background" in sent
    assert "full body reference" in sent


def test_generate_scene_prompt_no_turnaround(tmp_path, monkeypatch):
    """场景/道具类不注入角色三视图约束（它们就该带场景）。"""
    _patch_capturing(monkeypatch)
    pdir = _make_project(tmp_path)
    r = client.post("/assets/refs/generate", json={
        "project": str(pdir), "kind": "scenes",
        "entity_id": "咖啡馆", "prompt": "温馨咖啡馆"})
    assert r.status_code == 200, r.text
    sent = _CapturingProvider.last_prompt
    assert sent == "温馨咖啡馆"
    assert "three-view" not in sent
    assert "no scene background" not in sent


# ---------- 项目风格圣经注入（根因修复 #1） ----------

def _fake_manifest_with_style(style_ref):
    """造一个最小 manifest stub（只需 style_bible.ref 字段）。"""
    class _M:
        style_bible = {"ref": style_ref}
    return _M()


def test_generate_injects_project_style_bible(tmp_path, monkeypatch):
    """根因修复：generate 时读项目 style_bible.ref → 注入风格圣经关键词到 prompt。

    原 bug：/refs/generate 不读项目风格，出图用 provider 默认风格（如 2D）而非
    项目设定（电影冷调）。修复后 provider 收到的 prompt 必须含该风格的 suffix。
    """
    _patch_capturing(monkeypatch)
    pdir = _make_project(tmp_path)
    # monkeypatch manifest → 项目风格为「电影冷调」(real/cinematic-cool-v1)
    monkeypatch.setattr(
        assets_mod, "load_manifest",
        lambda _p: _fake_manifest_with_style("real/cinematic-cool-v1"))

    r = client.post("/assets/refs/generate", json={
        "project": str(pdir), "kind": "characters",
        "entity_id": "女主", "prompt": "红衣少女"})
    assert r.status_code == 200, r.text
    sent = _CapturingProvider.last_prompt
    # 原始描述 + 角色三视图约束仍在
    assert "红衣少女" in sent
    assert "three-view" in sent
    # 注入了「电影冷调」风格 suffix（teal-and-orange cool grade）
    assert "teal-and-orange cool grade" in sent
    # ref 阶段含视觉指纹（中性平光锁一致性）
    assert "neutral studio flat lighting" in sent


def test_generate_falls_back_to_idea_json_style(tmp_path, monkeypatch):
    """manifest 无风格时回退读 创意.json input.style_bible.ref。"""
    _patch_capturing(monkeypatch)
    pdir = _make_project(tmp_path)
    # manifest 无 style_bible.ref（空）
    monkeypatch.setattr(
        assets_mod, "load_manifest",
        lambda _p: _fake_manifest_with_style(""))
    # 创意.json 提供风格（2D 动画）
    (pdir / "创意.json").write_text(
        json.dumps({"input": {"style_bible": {"ref": "2D/anime-cel-v1"}}},
                   ensure_ascii=False),
        encoding="utf-8")

    r = client.post("/assets/refs/generate", json={
        "project": str(pdir), "kind": "scenes",
        "entity_id": "教室", "prompt": "明亮教室"})
    assert r.status_code == 200, r.text
    sent = _CapturingProvider.last_prompt
    assert "明亮教室" in sent
    assert "anime cel-shaded" in sent


def test_generate_no_style_keeps_prompt_unchanged(tmp_path, monkeypatch):
    """无项目风格（manifest 空 + 无 创意.json）→ prompt 原样（仅角色增广），不崩。"""
    _patch_capturing(monkeypatch)
    pdir = _make_project(tmp_path)
    monkeypatch.setattr(
        assets_mod, "load_manifest",
        lambda _p: _fake_manifest_with_style(""))
    r = client.post("/assets/refs/generate", json={
        "project": str(pdir), "kind": "scenes",
        "entity_id": "广场", "prompt": "城市广场"})
    assert r.status_code == 200, r.text
    sent = _CapturingProvider.last_prompt
    assert sent == "城市广场"
