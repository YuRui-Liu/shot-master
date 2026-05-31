"""T2① — main 启动序列接 SplashScreen 的装配测试。

offscreen 运行；monkeypatch AppShell / lifecycle / 真实 splash 为轻量假对象，
只验证 _run_with_splash 装配函数：splash 被创建 + show + 分阶段推进 + 最后 close，
且不破坏 _maybe_run_agent 既有逻辑。
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from drama_shot_master import main as main_mod


def _app():
    return QApplication.instance() or QApplication([])


class _FakeSplash:
    """记录 splash 生命周期调用，避免真窗口/绘制。"""

    def __init__(self):
        self.shown = False
        self.closed = False
        self.stages: list[tuple[int, str]] = []
        self.progress_calls: list[float] = []
        self.credits: tuple[str, str] | None = None
        self.tips: list[str] = []

    def show(self):
        self.shown = True

    def close(self):
        self.closed = True

    def set_stage(self, idx, state):
        self.stages.append((idx, state))

    def set_progress(self, value):
        self.progress_calls.append(value)

    def set_credits(self, author, business=""):
        self.credits = (author, business)

    def set_tip(self, text):
        self.tips.append(text)


class _FakeShell:
    """轻量假 AppShell：构造即记录，避免真 UI 装配。"""

    instances: list["_FakeShell"] = []

    def __init__(self, cfg=None):
        self.cfg = cfg
        self.shown = False
        self.screenwriter_lifecycle = None
        _FakeShell.instances.append(self)

    def show(self):
        self.shown = True


def _make_cfg():
    """最小 cfg 替身，覆盖 _run_with_splash 内取的字段。"""
    class _Cfg:
        screenwriter_agent_port = 8765
        screenwriter_stage_assignments = {}
        llm_providers = {}
    return _Cfg()


def _make_lifecycle():
    class _LC:
        def __init__(self):
            self.terminated = False

        def spawn(self):
            return 8765

        def is_alive(self):
            return True

        def terminate(self):
            self.terminated = True
    return _LC()


def test_maybe_run_agent_unaffected_no_flag():
    """无 --run-agent → 返回 None（既有分发逻辑不破坏）。"""
    assert main_mod._maybe_run_agent(["app"]) is None


def test_maybe_run_agent_unknown_returns_none():
    assert main_mod._maybe_run_agent(["app", "--run-agent", "nope"]) is None


def test_run_with_splash_lifecycle(monkeypatch):
    """splash 被 show、分阶段推进（active→done）、最后 close，主窗 show。"""
    _app()
    _FakeShell.instances.clear()
    fake_splash = _FakeSplash()
    fake_lc = _make_lifecycle()

    monkeypatch.setattr(main_mod, "SplashScreen", lambda: fake_splash, raising=False)

    cfg = _make_cfg()
    shell = main_mod._run_with_splash(
        cfg,
        shell_factory=_FakeShell,
        lifecycle_factory=lambda **kw: fake_lc,
    )

    # splash 走完整生命周期
    assert fake_splash.shown is True
    assert fake_splash.closed is True
    # 三步都至少被推进过（active 与 done）
    assert any(s == (0, "active") for s in fake_splash.stages)
    assert any(s == (2, "done") for s in fake_splash.stages)
    # 阶段顺序：第 0 步 active 早于第 2 步 done
    idx_first_active = next(i for i, s in enumerate(fake_splash.stages)
                            if s == (0, "active"))
    idx_last_done = next(i for i, s in enumerate(fake_splash.stages)
                         if s == (2, "done"))
    assert idx_first_active < idx_last_done
    # 主窗构造 + show，端口回写
    assert shell is _FakeShell.instances[-1]
    assert shell.shown is True
    assert shell.screenwriter_lifecycle is fake_lc
    assert cfg.screenwriter_agent_port == 8765


def test_run_with_splash_close_before_show(monkeypatch):
    """splash.close 应在主窗 show 之前（避免 splash 盖主窗）。"""
    _app()
    _FakeShell.instances.clear()
    order: list[str] = []

    class _OrderSplash(_FakeSplash):
        def close(self):
            super().close()
            order.append("splash_close")

    class _OrderShell(_FakeShell):
        def show(self):
            super().show()
            order.append("shell_show")

    fake_splash = _OrderSplash()
    monkeypatch.setattr(main_mod, "SplashScreen", lambda: fake_splash, raising=False)

    main_mod._run_with_splash(
        _make_cfg(),
        shell_factory=_OrderShell,
        lifecycle_factory=lambda **kw: _make_lifecycle(),
    )

    assert "splash_close" in order and "shell_show" in order
    assert order.index("splash_close") < order.index("shell_show")
