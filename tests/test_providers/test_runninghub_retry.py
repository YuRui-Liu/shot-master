"""RunningHubClient 瞬时网络/SSL 错误指数退避重试单测。

真机症状：query_task 轮询遇瞬时 SSL 断连
（'EOF occurred in violation of protocol (_ssl.c:1007)'）即放弃。
本套测试验证 query_task / create_task / upload_file 对瞬时错误重试、
对业务错或重试耗尽抛错；monkeypatch _sleep 免真等。
"""
from __future__ import annotations

import ssl

import httpx
import pytest

from drama_shot_master.providers import runninghub as rh
from drama_shot_master.providers.runninghub import (
    RunningHubClient, RunningHubUnavailable, RunningHubTaskFailed,
    RunningHubUploadError,
    _is_transient_error, _retry_transient,
    _RETRY_ATTEMPTS,
)


# ---------- _is_transient_error 分类 ----------

@pytest.mark.parametrize("exc", [
    httpx.ConnectError("refused"),
    httpx.ReadError("read"),
    httpx.WriteError("write"),
    httpx.RemoteProtocolError("server disconnected"),
    ssl.SSLError("EOF occurred in violation of protocol (_ssl.c:1007)"),
    httpx.ConnectError("EOF occurred in violation of protocol (_ssl.c:1007)"),
    RuntimeError("wrapped _ssl.c:1007 EOF"),
])
def test_transient_errors_detected(exc):
    assert _is_transient_error(exc) is True


@pytest.mark.parametrize("exc", [
    ValueError("bad json"),
    KeyError("fileName"),
    RunningHubTaskFailed("business error 805"),
    RuntimeError("totally unrelated"),
])
def test_non_transient_errors_not_detected(exc):
    assert _is_transient_error(exc) is False


# ---------- _retry_transient 退避行为 ----------

def test_retry_succeeds_after_n_transient_failures(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(rh, "_sleep", lambda s: slept.append(s))

    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] <= 2:  # 前 2 次瞬时失败，第 3 次成功
            raise ssl.SSLError("EOF occurred in violation of protocol (_ssl.c:1007)")
        return "ok"

    assert _retry_transient(fn) == "ok"
    assert calls["n"] == 3
    assert slept == [1.0, 2.0]  # 退避 1s, 2s


def test_retry_exhausts_and_reraises(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(rh, "_sleep", lambda s: slept.append(s))

    def fn():
        raise httpx.ConnectError("EOF occurred in violation of protocol")

    with pytest.raises(httpx.ConnectError):
        _retry_transient(fn)
    # _RETRY_ATTEMPTS 次尝试 → _RETRY_ATTEMPTS-1 次退避
    assert len(slept) == _RETRY_ATTEMPTS - 1
    assert slept == [1.0, 2.0, 4.0]


def test_retry_does_not_retry_non_transient(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(rh, "_sleep", lambda s: slept.append(s))

    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise RunningHubTaskFailed("business")

    with pytest.raises(RunningHubTaskFailed):
        _retry_transient(fn)
    assert calls["n"] == 1  # 不重试
    assert slept == []


# ---------- 端点级：注入 httpx 错误验证重试 ----------

def _flaky_transport(fail_times: int, final_response: httpx.Response,
                     exc_factory):
    """前 fail_times 次抛 exc_factory()，之后返回 final_response。"""
    state = {"n": 0}

    def handler(req):
        state["n"] += 1
        if state["n"] <= fail_times:
            raise exc_factory()
        return final_response

    return handler, state


def test_query_task_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(rh, "_sleep", lambda s: None)

    ok = httpx.Response(200, json={
        "taskId": "tid", "status": "RUNNING",
        "errorCode": "", "errorMessage": "", "results": None,
    })
    handler, state = _flaky_transport(
        2, ok,
        lambda: ssl.SSLError(
            "EOF occurred in violation of protocol (_ssl.c:1007)"))

    c = RunningHubClient("k")
    c._client = httpx.Client(transport=httpx.MockTransport(handler))

    d = c.query_task("tid")
    assert d["status"] == "RUNNING"
    assert state["n"] == 3  # 失败 2 次 + 成功 1 次


def test_query_task_all_transient_failures_raise(monkeypatch):
    monkeypatch.setattr(rh, "_sleep", lambda s: None)

    def handler(req):
        raise httpx.ReadError(
            "EOF occurred in violation of protocol (_ssl.c:1007)")

    c = RunningHubClient("k")
    c._client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(RunningHubUnavailable):
        c.query_task("tid")


def test_query_task_business_5xx_not_retried(monkeypatch):
    """HTTP 5xx 不抛 httpx 异常 → 不进重试，直接 Unavailable，仅调用 1 次。"""
    slept: list[float] = []
    monkeypatch.setattr(rh, "_sleep", lambda s: slept.append(s))

    state = {"n": 0}

    def handler(req):
        state["n"] += 1
        return httpx.Response(503)

    c = RunningHubClient("k")
    c._client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(RunningHubUnavailable):
        c.query_task("tid")
    assert state["n"] == 1
    assert slept == []


def test_create_task_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(rh, "_sleep", lambda s: None)

    ok = httpx.Response(200, json={
        "code": 0, "msg": "success", "data": {"taskId": "tid-x"}})
    handler, state = _flaky_transport(
        1, ok, lambda: httpx.RemoteProtocolError("server disconnected"))

    c = RunningHubClient("k")
    c._client = httpx.Client(transport=httpx.MockTransport(handler))

    task_id = c.create_task(workflow_id="wf-1")
    assert task_id == "tid-x"
    assert state["n"] == 2


def test_create_task_all_failures_raise_unavailable(monkeypatch):
    monkeypatch.setattr(rh, "_sleep", lambda s: None)

    def handler(req):
        raise httpx.ConnectError("EOF _ssl.c:1007")

    c = RunningHubClient("k")
    c._client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(RunningHubUnavailable):
        c.create_task(workflow_id="wf-1")


def _png_bytes() -> bytes:
    return (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90"
            b"wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe"
            b"\x02\xfe\xdc\xccY\xe7\x00\x00\x00\x00IEND\xaeB`\x82")


def test_upload_file_retries_then_succeeds(monkeypatch, tmp_path):
    monkeypatch.setattr(rh, "_sleep", lambda s: None)

    img = tmp_path / "a.png"
    img.write_bytes(_png_bytes())

    bodies: list[bytes] = []
    state = {"n": 0}

    def handler(req):
        state["n"] += 1
        bodies.append(req.read())  # 验证每次重试 body 非空
        if state["n"] <= 2:
            raise ssl.SSLError("EOF occurred in violation of protocol (_ssl.c:1007)")
        return httpx.Response(200, json={
            "code": 0, "data": {"fileName": "openapi/a.png"}})

    c = RunningHubClient("k")
    c._client = httpx.Client(transport=httpx.MockTransport(handler))

    name = c.upload_file(img)
    assert name == "openapi/a.png"
    assert state["n"] == 3
    # 重试时文件被重新打开，每次都带完整 multipart body
    assert all(b'name="file"' in b for b in bodies)


def test_upload_file_all_failures_raise_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(rh, "_sleep", lambda s: None)

    img = tmp_path / "a.png"
    img.write_bytes(_png_bytes())

    def handler(req):
        raise httpx.ConnectError("EOF _ssl.c:1007")

    c = RunningHubClient("k")
    c._client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(RunningHubUnavailable):
        c.upload_file(img)


def test_upload_file_missing_file_not_retried(monkeypatch, tmp_path):
    """本地文件不存在是即时业务错，不应进重试。"""
    slept: list[float] = []
    monkeypatch.setattr(rh, "_sleep", lambda s: slept.append(s))

    c = RunningHubClient("k")
    with pytest.raises(RunningHubUploadError):
        c.upload_file(tmp_path / "nope.png")
    assert slept == []
