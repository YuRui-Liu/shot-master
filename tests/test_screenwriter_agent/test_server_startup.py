def test_create_app_returns_fastapi():
    from screenwriter_agent.server import create_app
    app = create_app()
    # 必须含 /health 路由（Task 10 加；此时通过空 app + 占位 stub 路由也行）
    paths = {r.path for r in app.routes}
    assert "/health" in paths
