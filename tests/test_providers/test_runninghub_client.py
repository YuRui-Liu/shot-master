"""RunningHubClient 单测（mock httpx）。"""
from __future__ import annotations

import pytest
from pathlib import Path
import httpx

from app.providers.runninghub import RunningHubClient
from app.providers.runninghub import (
    RunningHubUnavailable, RunningHubTaskFailed,
    RunningHubUploadError, RunningHubInvalidSpec,
)


def test_exception_classes_are_distinct():
    assert issubclass(RunningHubUnavailable, Exception)
    assert issubclass(RunningHubTaskFailed, Exception)
    assert issubclass(RunningHubUploadError, Exception)
    assert issubclass(RunningHubInvalidSpec, Exception)
    # 都是独立类，互不继承
    for a, b in [
        (RunningHubUnavailable, RunningHubTaskFailed),
        (RunningHubUploadError, RunningHubTaskFailed),
        (RunningHubInvalidSpec, RunningHubUnavailable),
    ]:
        assert not issubclass(a, b) and not issubclass(b, a)


# ---------- init / 基础 ----------

def test_init_rejects_empty_api_key():
    with pytest.raises(RunningHubUnavailable):
        RunningHubClient("")


def test_init_strips_base_url_trailing_slash():
    c = RunningHubClient("k", base_url="https://x.com/")
    assert c.base_url == "https://x.com"


def test_init_default_base_url():
    c = RunningHubClient("k")
    assert c.base_url == "https://www.runninghub.cn"


# ---------- upload_file ----------

def _png_bytes() -> bytes:
    # 1x1 PNG
    return (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90"
            b"wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe"
            b"\x02\xfe\xdc\xccY\xe7\x00\x00\x00\x00IEND\xaeB`\x82")


def _set_mock_transport(client: RunningHubClient, handler):
    """把 RunningHubClient._client 换成 MockTransport 客户端。"""
    client._client = httpx.Client(transport=httpx.MockTransport(handler))


def test_upload_file_happy_path(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(_png_bytes())

    captured = {}

    def handler(req):
        captured["url"] = str(req.url)
        captured["auth"] = req.headers.get("Authorization")
        captured["body"] = req.read()
        return httpx.Response(200, json={
            "code": 0, "message": "success",
            "data": {"type": "image",
                     "download_url": "https://x/a.png",
                     "fileName": "openapi/abc.png",
                     "size": "1234"},
        })

    c = RunningHubClient("test-key")
    _set_mock_transport(c, handler)
    name = c.upload_file(img)
    assert name == "openapi/abc.png"
    assert captured["url"].endswith("/openapi/v2/media/upload/binary")
    assert captured["auth"] == "Bearer test-key"
    assert b'name="file"' in captured["body"]


def test_upload_file_raises_on_missing_local_file(tmp_path):
    c = RunningHubClient("k")
    with pytest.raises(RunningHubUploadError):
        c.upload_file(tmp_path / "nonexistent.png")


def test_upload_file_raises_on_http_4xx(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(_png_bytes())

    def handler(req):
        return httpx.Response(401, text="unauthorized")

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    with pytest.raises(RunningHubUploadError) as exc_info:
        c.upload_file(img)
    assert "401" in str(exc_info.value)


def test_upload_file_raises_unavailable_on_connect_error(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(_png_bytes())

    def handler(req):
        raise httpx.ConnectError("connection refused")

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    with pytest.raises(RunningHubUnavailable):
        c.upload_file(img)


def test_upload_file_raises_on_business_error_code(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(_png_bytes())

    def handler(req):
        return httpx.Response(200, json={
            "code": 1001, "msg": "余额不足", "data": None})

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    with pytest.raises(RunningHubUploadError) as exc_info:
        c.upload_file(img)
    assert "余额不足" in str(exc_info.value) or "1001" in str(exc_info.value)


def test_upload_file_mime_inferred_from_extension(tmp_path):
    img = tmp_path / "x.jpg"
    img.write_bytes(_png_bytes())   # 内容无所谓，扩展名决定 mime

    captured = {}

    def handler(req):
        captured["body"] = req.read()
        return httpx.Response(200, json={
            "code": 0, "data": {"fileName": "openapi/x.jpg"}})

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    c.upload_file(img)
    assert b"image/jpeg" in captured["body"]


# ---------- create_task ----------

def _ok_create_response(task_id="tid-1", status="QUEUED"):
    return httpx.Response(200, json={
        "code": 0, "msg": "success",
        "data": {
            "netWssUrl": "wss://x",
            "taskId": task_id,
            "clientId": "cid",
            "taskStatus": status,
            "promptTips": "{\"result\": true}",
        },
    })


def test_create_task_inline_workflow():
    captured = {}

    def handler(req):
        captured["url"] = str(req.url)
        captured["body"] = req.read()
        return _ok_create_response("tid-42")

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    task_id = c.create_task(workflow={"3": {"class_type": "VAE"}})
    assert task_id == "tid-42"
    assert captured["url"].endswith("/task/openapi/create")
    body = captured["body"].decode()
    assert '"workflow"' in body
    assert '"workflowId"' not in body


def test_create_task_with_workflow_id_and_node_info_list():
    captured = {}

    def handler(req):
        captured["body"] = req.read()
        return _ok_create_response("tid-2")

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    items = [{"nodeId": "46", "fieldName": "global_prompt",
              "fieldValue": "hello"}]
    task_id = c.create_task(workflow_id="wf-123", node_info_list=items)
    assert task_id == "tid-2"
    body = captured["body"].decode()
    # workflowId 字段在 payload 里
    assert '"workflowId":"wf-123"' in body.replace(" ", "")
    assert '"nodeInfoList"' in body
    # workflow 字段不应单独出现（"workflowId" 里的 "workflow" 子串不算）
    # 把 workflowId 删了再判断 workflow 是否出现
    body_no_wfid = body.replace('"workflowId"', "")
    assert '"workflow"' not in body_no_wfid


def test_create_task_rejects_when_both_workflow_and_id_missing():
    c = RunningHubClient("k")
    with pytest.raises(RunningHubInvalidSpec):
        c.create_task()


def test_create_task_passes_webhook_url():
    captured = {}

    def handler(req):
        captured["body"] = req.read()
        return _ok_create_response()

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    c.create_task(workflow={}, webhook_url="https://callback/x")
    assert b"https://callback/x" in captured["body"]


def test_create_task_business_error_includes_prompt_tips():
    def handler(req):
        return httpx.Response(200, json={
            "code": 805, "msg": "validation failed",
            "data": {"promptTips":
                     "{\"node_errors\": {\"46\": \"invalid\"}}"},
        })

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    with pytest.raises(RunningHubTaskFailed) as exc_info:
        c.create_task(workflow={})
    msg = str(exc_info.value)
    assert "805" in msg
    assert "validation failed" in msg


def test_create_task_http_5xx_raises_task_failed():
    def handler(req):
        return httpx.Response(503, text="service unavailable")

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    with pytest.raises(RunningHubTaskFailed) as exc_info:
        c.create_task(workflow={})
    assert "503" in str(exc_info.value)


def test_create_task_connect_error_raises_unavailable():
    def handler(req):
        raise httpx.ConnectError("refused")

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    with pytest.raises(RunningHubUnavailable):
        c.create_task(workflow={})


# ---------- query_task ----------

def test_query_task_v2_flat_shape():
    """V2 endpoint returns flat dict (no code/msg/data wrapper)."""
    captured = {}

    def handler(req):
        captured["url"] = str(req.url)
        captured["body"] = req.read()
        return httpx.Response(200, json={
            "taskId": "tid", "status": "RUNNING",
            "errorCode": "", "errorMessage": "",
            "results": None, "clientId": "",
            "promptTips": "", "failedReason": {},
        })

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    d = c.query_task("tid")
    assert d["status"] == "RUNNING"
    assert d["results"] is None
    assert d["taskId"] == "tid"
    assert captured["url"].endswith("/openapi/v2/query")
    assert b"tid" in captured["body"]


def test_query_task_legacy_string_data_compat():
    def handler(req):
        return httpx.Response(200, json={
            "code": 0, "msg": "", "data": "SUCCESS"})

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    d = c.query_task("tid")
    assert d == {"status": "SUCCESS", "results": None,
                  "errorCode": "", "errorMessage": ""}


def test_query_task_success_with_results_flat():
    """V2 SUCCESS response is flat dict with results array."""
    def handler(req):
        return httpx.Response(200, json={
            "taskId": "tid", "status": "SUCCESS",
            "errorCode": "", "errorMessage": "",
            "results": [{"url": "https://x/v.mp4",
                          "outputType": "mp4"}],
            "clientId": "", "promptTips": "",
        })

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    d = c.query_task("tid")
    assert d["status"] == "SUCCESS"
    assert d["results"] == [{"url": "https://x/v.mp4", "outputType": "mp4"}]


def test_query_task_connect_error_raises_unavailable():
    def handler(req):
        raise httpx.ConnectError("refused")

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    with pytest.raises(RunningHubUnavailable):
        c.query_task("tid")


def test_query_task_5xx_raises_unavailable():
    def handler(req):
        return httpx.Response(503)

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    with pytest.raises(RunningHubUnavailable):
        c.query_task("tid")


def test_query_task_unknown_shape_raises_unavailable():
    """既没有 status 也没有 code 字段 → 抛 Unavailable。"""
    def handler(req):
        return httpx.Response(200, json={"unrelated": "junk"})

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    with pytest.raises(RunningHubUnavailable, match="响应形状未知"):
        c.query_task("tid")


# ---------- download_file ----------

def test_download_file_streams_to_dest(tmp_path):
    payload = b"a" * 5000

    def handler(req):
        return httpx.Response(200, content=payload)

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    dest = tmp_path / "sub" / "out.mp4"
    result = c.download_file("https://x/v.mp4", dest)
    assert result == dest
    assert dest.read_bytes() == payload
    assert dest.parent.exists()


def test_download_file_raises_on_404(tmp_path):
    def handler(req):
        return httpx.Response(404)

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    with pytest.raises(RunningHubUnavailable):
        c.download_file("https://x/v.mp4", tmp_path / "v.mp4")


# ---------- cancel_task ----------

def test_cancel_task_silent_on_error():
    def handler(req):
        raise httpx.ConnectError("refused")

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    # 不应抛错
    c.cancel_task("tid")


def test_cancel_task_silent_on_4xx():
    def handler(req):
        return httpx.Response(400)

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    c.cancel_task("tid")


# ---------- get_account_status ----------

def test_account_status_happy_path():
    def handler(req):
        assert req.url.path == "/uc/openapi/accountStatus"
        assert req.headers.get("Authorization") == "Bearer test-key"
        body = req.read().decode()
        assert '"apikey"' in body  # lowercase!
        return httpx.Response(200, json={
            "code": 0, "msg": "success", "errorMessages": None,
            "data": {
                "remainCoins": "38752",
                "currentTaskCounts": "0",
                "remainMoney": "21.780",
                "currency": "CNY",
                "apiType": "SHARED",
            },
        })

    c = RunningHubClient("test-key")
    _set_mock_transport(c, handler)
    data = c.get_account_status()
    assert data["remainCoins"] == "38752"
    assert data["apiType"] == "SHARED"


def test_account_status_business_error_raises_unavailable():
    def handler(req):
        return httpx.Response(200, json={
            "code": 401, "msg": "Invalid API key", "data": None})

    c = RunningHubClient("bad-key")
    _set_mock_transport(c, handler)
    with pytest.raises(RunningHubUnavailable) as exc_info:
        c.get_account_status()
    assert "401" in str(exc_info.value) or "Invalid API key" in str(exc_info.value)


def test_account_status_5xx_raises_unavailable():
    def handler(req):
        return httpx.Response(503, text="upstream timeout")
    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    with pytest.raises(RunningHubUnavailable):
        c.get_account_status()


def test_account_status_connect_error_raises_unavailable():
    def handler(req):
        raise httpx.ConnectError("network down")
    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    with pytest.raises(RunningHubUnavailable):
        c.get_account_status()


# ---------- context manager ----------

def test_context_manager_closes_client():
    c = RunningHubClient("k")
    with c as got:
        assert got is c
    assert c._client.is_closed
