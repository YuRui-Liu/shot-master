def test_lifecycle_module_importable():
    from drama_shot_master.agents.screenwriter_lifecycle import ScreenwriterLifecycle
    lc = ScreenwriterLifecycle()
    assert hasattr(lc, "spawn") and hasattr(lc, "terminate") and hasattr(lc, "port")


def test_agent_command_dev_uses_dash_m(monkeypatch):
    """开发态（未冻结）：用 python -m screenwriter_agent。"""
    import drama_shot_master.agents.screenwriter_lifecycle as lc
    monkeypatch.setattr(lc, "_is_frozen", lambda: False)
    cmd = lc._agent_command(18430)
    assert cmd[1:3] == ["-m", "screenwriter_agent"]
    assert "--port" in cmd and "18430" in cmd


def test_agent_command_frozen_uses_run_agent(monkeypatch):
    """冻结态（Nuitka）：同一 exe 用 --run-agent screenwriter。"""
    import drama_shot_master.agents.screenwriter_lifecycle as lc
    monkeypatch.setattr(lc, "_is_frozen", lambda: True)
    cmd = lc._agent_command(18430)
    assert "-m" not in cmd
    assert cmd[1:3] == ["--run-agent", "screenwriter"]
    assert "--port" in cmd and "18430" in cmd


def test_maybe_run_agent_dispatches(monkeypatch):
    """main 入口：--run-agent screenwriter → 跑 agent，返回其退出码。"""
    import drama_shot_master.main as m
    called = {}
    def _fake_agent_main(argv):
        called["argv"] = argv
        return 0
    monkeypatch.setattr(
        "screenwriter_agent.__main__.main", _fake_agent_main, raising=True)
    rc = m._maybe_run_agent(
        ["main.exe", "--run-agent", "screenwriter", "--port", "9"])
    assert rc == 0
    assert called["argv"] == ["--port", "9"]


def test_maybe_run_agent_none_for_gui(monkeypatch):
    """普通启动（无 --run-agent）→ 返回 None，继续走 GUI。"""
    import drama_shot_master.main as m
    assert m._maybe_run_agent(["main.exe"]) is None


# ── 修 Windows venv 启动器 PID 不匹配 → 误杀 agent / 误报死亡 ──────────

def test_health_matches_helper():
    from drama_shot_master.agents.screenwriter_lifecycle import _health_matches
    assert _health_matches({"nonce": "abc"}, "abc") is True
    assert _health_matches({"nonce": "xyz"}, "abc") is False
    assert _health_matches({}, "abc") is False
    assert _health_matches({"nonce": "x"}, "") is True   # 无期望 nonce → 宽松


def test_health_route_returns_nonce(monkeypatch):
    monkeypatch.setenv("SCREENWRITER_AGENT_NONCE", "tok123")
    from fastapi.testclient import TestClient
    from screenwriter_agent.server import create_app
    c = TestClient(create_app())
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json().get("nonce") == "tok123"


def test_is_alive_via_health_when_proc_exited(monkeypatch):
    """启动器壳退出(poll!=None)但 /health 匹配 → 仍视为存活（Windows venv 修复）。"""
    from drama_shot_master.agents.screenwriter_lifecycle import ScreenwriterLifecycle
    lc = ScreenwriterLifecycle()
    lc._nonce = "tok"                 # 模拟已 spawn

    class _DeadProc:
        def poll(self):
            return 0          # 已退出
    lc._proc = _DeadProc()
    monkeypatch.setattr(lc, "_health_ok", lambda port: True)
    assert lc.is_alive() is True


def test_is_alive_false_when_proc_exited_and_health_fails(monkeypatch):
    from drama_shot_master.agents.screenwriter_lifecycle import ScreenwriterLifecycle
    lc = ScreenwriterLifecycle()

    class _DeadProc:
        def poll(self):
            return 0
    lc._proc = _DeadProc()
    monkeypatch.setattr(lc, "_health_ok", lambda port: False)
    assert lc.is_alive() is False
