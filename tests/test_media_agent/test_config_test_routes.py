"""media_agent 测试连接端点 /config/test/llm + /config/test/runninghub —

无 Qt、零网络：monkeypatch 假 openai client / 假 httpx GET，断言 ok 与 fail 两路径。
"""
from fastapi.testclient import TestClient

from media_agent.routes import config_test as ct
from media_agent.server import create_app

client = TestClient(create_app())


# ---------- 假 openai client ----------

class _FakeCompletions:
    def __init__(self, exc=None):
        self._exc = exc
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._exc:
            raise self._exc
        return object()


class _FakeChat:
    def __init__(self, exc=None):
        self.completions = _FakeCompletions(exc)


class _FakeModels:
    def __init__(self, exc=None):
        self._exc = exc
        self.called = False

    def list(self):
        self.called = True
        if self._exc:
            raise self._exc
        return ["m1"]


class _FakeOpenAI:
    def __init__(self, *, exc=None, models_exc=None):
        self.chat = _FakeChat(exc)
        self.models = _FakeModels(models_exc)


# ---------- 假 httpx response ----------

class _FakeResp:
    def __init__(self, status_code):
        self.status_code = status_code


# ---------- /config/test/llm ----------

def test_llm_ok_with_model(monkeypatch):
    fake = _FakeOpenAI()
    monkeypatch.setattr(
        ct, "_make_openai_client",
        lambda **kw: fake)
    r = client.post("/config/test/llm", json={
        "base_url": "https://api.deepseek.com",
        "api_key": "sk-x",
        "model": "deepseek-chat",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert "deepseek-chat" in body["message"]
    # 走了 chat.completions，且 max_tokens=1
    assert fake.chat.completions.calls
    assert fake.chat.completions.calls[0]["max_tokens"] == 1
    assert fake.chat.completions.calls[0]["model"] == "deepseek-chat"


def test_llm_ok_without_model_lists(monkeypatch):
    fake = _FakeOpenAI()
    monkeypatch.setattr(ct, "_make_openai_client", lambda **kw: fake)
    r = client.post("/config/test/llm", json={
        "base_url": "https://api.openai.com/v1",
        "api_key": "sk-x",
    })
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert fake.models.called is True
    assert not fake.chat.completions.calls


def test_llm_fail_on_exception(monkeypatch):
    fake = _FakeOpenAI(exc=RuntimeError("401 unauthorized\nstacktrace line"))
    monkeypatch.setattr(ct, "_make_openai_client", lambda **kw: fake)
    r = client.post("/config/test/llm", json={
        "base_url": "https://api.deepseek.com",
        "api_key": "bad",
        "model": "deepseek-chat",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    # 只取首行、截断
    assert body["message"] == "401 unauthorized"


def test_llm_fail_on_client_construction(monkeypatch):
    def _boom(**kw):
        raise ValueError("bad base_url")
    monkeypatch.setattr(ct, "_make_openai_client", _boom)
    r = client.post("/config/test/llm", json={
        "base_url": "https://x", "api_key": "k"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "bad base_url" in body["message"]


def test_llm_missing_fields_no_call(monkeypatch):
    called = {"n": 0}

    def _factory(**kw):
        called["n"] += 1
        return _FakeOpenAI()
    monkeypatch.setattr(ct, "_make_openai_client", _factory)

    r = client.post("/config/test/llm", json={"base_url": "", "api_key": "k"})
    assert r.json() == {"ok": False, "message": "缺少 base_url"}
    r = client.post("/config/test/llm", json={"base_url": "u", "api_key": ""})
    assert r.json() == {"ok": False, "message": "缺少 api_key"}
    assert called["n"] == 0  # 缺字段不应构造 client


# ---------- /config/test/runninghub ----------

def test_runninghub_ok(monkeypatch):
    captured = {}

    def _get(url, *, headers, timeout):
        captured["url"] = url
        captured["headers"] = headers
        return _FakeResp(200)
    monkeypatch.setattr(ct, "_http_get", _get)

    r = client.post("/config/test/runninghub", json={
        "api_key": "rh-key", "base_url": "https://www.runninghub.cn/"})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    # base_url 去尾斜杠，带 Bearer
    assert captured["url"] == "https://www.runninghub.cn"
    assert captured["headers"]["Authorization"] == "Bearer rh-key"


def test_runninghub_default_base_url(monkeypatch):
    captured = {}

    def _get(url, **kw):
        captured["url"] = url
        return _FakeResp(200)
    monkeypatch.setattr(ct, "_http_get", _get)
    r = client.post("/config/test/runninghub", json={"api_key": "k"})
    assert r.json()["ok"] is True
    assert captured["url"] == "https://www.runninghub.cn"


def test_runninghub_auth_fail(monkeypatch):
    monkeypatch.setattr(ct, "_http_get", lambda url, **kw: _FakeResp(401))
    r = client.post("/config/test/runninghub", json={"api_key": "bad"})
    body = r.json()
    assert body["ok"] is False
    assert "401" in body["message"]


def test_runninghub_other_status(monkeypatch):
    monkeypatch.setattr(ct, "_http_get", lambda url, **kw: _FakeResp(500))
    r = client.post("/config/test/runninghub", json={"api_key": "k"})
    body = r.json()
    assert body["ok"] is False
    assert "500" in body["message"]


def test_runninghub_network_error(monkeypatch):
    def _boom(url, **kw):
        raise OSError("name resolution failed\nmore")
    monkeypatch.setattr(ct, "_http_get", _boom)
    r = client.post("/config/test/runninghub", json={"api_key": "k"})
    body = r.json()
    assert body["ok"] is False
    assert "连接失败" in body["message"]
    assert "name resolution failed" in body["message"]


def test_runninghub_missing_api_key(monkeypatch):
    called = {"n": 0}

    def _get(url, **kw):
        called["n"] += 1
        return _FakeResp(200)
    monkeypatch.setattr(ct, "_http_get", _get)
    r = client.post("/config/test/runninghub", json={"api_key": ""})
    assert r.json() == {"ok": False, "message": "缺少 api_key"}
    assert called["n"] == 0
