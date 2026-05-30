"""Toast 轻提示组件。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QWidget


def _app():
    return QApplication.instance() or QApplication([])


def test_show_toast_displays_text():
    _app()
    from drama_shot_master.ui.widgets.toast import show_toast
    host = QWidget(); host.resize(400, 300)
    t = show_toast(host, "✓ 已复制到剪贴板")
    assert t.text() == "✓ 已复制到剪贴板"
    assert not t.isHidden()                 # 显示后立即可见
    assert t.parentWidget() is host


def test_show_toast_reuses_single_widget():
    _app()
    from drama_shot_master.ui.widgets.toast import show_toast
    host = QWidget(); host.resize(400, 300)
    t1 = show_toast(host, "A")
    t2 = show_toast(host, "B")
    assert t1 is t2                          # 同一 host 复用一个 toast
    assert t2.text() == "B"


def test_toast_positioned_inside_parent():
    _app()
    from drama_shot_master.ui.widgets.toast import show_toast
    host = QWidget(); host.resize(400, 300)
    t = show_toast(host, "hi")
    # 落在 parent 内（底部居中，不越界）
    assert 0 <= t.x() <= host.width()
    assert 0 <= t.y() <= host.height()
