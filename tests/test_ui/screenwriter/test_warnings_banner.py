import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter._warnings_banner import _WarningsBanner


def _app():
    return QApplication.instance() or QApplication([])


def test_banner_hidden_when_no_warnings():
    _app()
    b = _WarningsBanner()
    b.set_warnings([])
    assert b.isVisible() is False


def test_banner_emits_path_on_click():
    _app()
    b = _WarningsBanner()
    b.set_warnings([
        {"path": "shots[1].stylePrompt", "issue": "过短", "severity": "warning"},
    ])
    got = []
    b.warningClicked.connect(got.append)
    # 模拟点击：直接 emit 内部（测试 helper）
    b._emit_click("shots[1].stylePrompt")
    assert got == ["shots[1].stylePrompt"]
