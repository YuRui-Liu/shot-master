"""media_agent 元信息端点 — 无 Qt（TestClient）。

验证 M0 收尾：CORS 中间件、/ui 静态同源托管、/openapi.json 契约。
"""
from fastapi.testclient import TestClient

from media_agent.server import create_app

client = TestClient(create_app())


def test_cors_header_present():
    """带 Origin 的请求应回 Access-Control-Allow-Origin（放行本地来源）。"""
    r = client.get("/health", headers={"Origin": "http://127.0.0.1:5500"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://127.0.0.1:5500"


def test_cors_allows_file_null_origin():
    """file:// 页 Origin 为 'null'，应被放行。"""
    r = client.get("/health", headers={"Origin": "null"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "null"


def test_cors_preflight():
    """OPTIONS 预检应返回放行方法头。"""
    r = client.options(
        "/health",
        headers={
            "Origin": "http://127.0.0.1:5500",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code in (200, 204)
    assert "access-control-allow-origin" in {k.lower() for k in r.headers}


def test_ui_static_serves_html():
    """/ui/ 静态托管：已知页面经同源 HTTP 可取到 HTML。"""
    r = client.get("/ui/split-tool.html")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert "<" in r.text  # 是 HTML 文档


def test_openapi_has_paths():
    r = client.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    assert isinstance(schema.get("paths"), dict)
    assert schema["paths"]  # 非空
    assert "/health" in schema["paths"]
