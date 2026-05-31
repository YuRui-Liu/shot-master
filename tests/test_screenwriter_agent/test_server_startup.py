def test_create_app_returns_fastapi():
    from screenwriter_agent.server import create_app
    app = create_app()
    # 必须含 /health 路由（Task 10 加；此时通过空 app + 占位 stub 路由也行）
    paths = {r.path for r in app.routes}
    assert "/health" in paths


def test_cors_header_present_for_local_origin():
    """带本地 Origin（如 /ui 同源页 18450）的请求应回 Access-Control-Allow-Origin。

    编剧 Web 页从 media_agent 同源页跨端口 fetch 本 agent SSE，需放行 CORS。
    """
    from fastapi.testclient import TestClient
    from screenwriter_agent.server import create_app

    client = TestClient(create_app())
    r = client.get("/health", headers={"Origin": "http://127.0.0.1:18450"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://127.0.0.1:18450"


def test_cors_allows_file_null_origin():
    """file:// 页 Origin 为 'null'，应被放行。"""
    from fastapi.testclient import TestClient
    from screenwriter_agent.server import create_app

    client = TestClient(create_app())
    r = client.get("/health", headers={"Origin": "null"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "null"
