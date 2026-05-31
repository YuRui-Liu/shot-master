import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.title_bar import FramelessTitleBar


def _app():
    return QApplication.instance() or QApplication([])


def test_constructs_and_has_three_window_controls():
    """构造不崩；三窗控按钮（最小化/最大化/关闭）+ 全局设置按钮存在。"""
    _app()
    bar = FramelessTitleBar()
    assert bar.btn_min is not None
    assert bar.btn_max is not None
    assert bar.btn_close is not None
    assert bar.btn_settings is not None
    # 固定高 ~38
    assert bar.height() == 38


def test_settings_requested_emits():
    """点「⚙ 全局设置」→ settingsRequested 发射。"""
    _app()
    bar = FramelessTitleBar()
    fired = {}
    bar.settingsRequested.connect(lambda: fired.setdefault("ok", True))
    bar.btn_settings.click()
    assert fired.get("ok") is True


def test_max_toggle_does_not_crash_with_mock_window():
    """最大化按钮 toggle 不崩——用 mock window 模拟 isMaximized/show* 切换。"""
    _app()
    bar = FramelessTitleBar()

    class _FakeWin:
        def __init__(self):
            self._max = False
            self.calls = []

        def isMaximized(self):
            return self._max

        def showMaximized(self):
            self._max = True
            self.calls.append("max")

        def showNormal(self):
            self._max = False
            self.calls.append("normal")

    fake = _FakeWin()
    bar.window = lambda: fake   # 替身

    # 初始非最大化 → toggle → 最大化，图标切 ❐
    bar._on_toggle_max()
    assert fake._max is True
    assert bar.btn_max.text() == "❐"
    # 再 toggle → 还原，图标切回 □
    bar._on_toggle_max()
    assert fake._max is False
    assert bar.btn_max.text() == "□"
    assert fake.calls == ["max", "normal"]


def test_minimize_and_close_route_to_window():
    """➖ → window.showMinimized；✕ → window.close（mock 验证调用）。"""
    _app()
    bar = FramelessTitleBar()

    class _FakeWin:
        def __init__(self):
            self.minimized = False
            self.closed = False

        def showMinimized(self):
            self.minimized = True

        def close(self):
            self.closed = True

    fake = _FakeWin()
    bar.window = lambda: fake
    bar._on_minimize()
    bar._on_close()
    assert fake.minimized is True
    assert fake.closed is True
