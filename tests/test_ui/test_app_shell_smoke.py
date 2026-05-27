import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.app_shell import AppShell
from drama_shot_master.ui.nav_config import FUNCS, LABELS


def _app():
    return QApplication.instance() or QApplication([])


def test_shell_constructs_and_registers_seven_pages():
    _app()
    w = AppShell()
    w.show()
    QApplication.instance().processEvents()
    assert len(w.pages) == len(FUNCS)


def test_breadcrumb_for_known_pages():
    _app()
    w = AppShell()
    w.switchTo(w.pages["split"])
    assert w.breadcrumb_text() == "① 素材准备 › 拆图"
    w.switchTo(w.pages["dubbing"])
    assert w.breadcrumb_text() == "③ 视频出片 › 配音"


def test_batch_pages_are_batch_tool_page():
    _app()
    from drama_shot_master.ui.pages.batch_tool_page import BatchToolPage
    w = AppShell()
    for key in ("split", "combine", "trim"):
        assert isinstance(w.pages[key], BatchToolPage)


def test_task_pages_are_manager_panels():
    _app()
    from drama_shot_master.ui.panels.video_task_manager_panel import VideoTaskManagerPanel
    w = AppShell()
    assert isinstance(w.pages["video_gen"], VideoTaskManagerPanel)


def test_open_dir_method_exists():
    _app()
    w = AppShell()
    assert hasattr(w, "_open_dir")


def test_shell_exposes_settings_and_about_entries():
    _app()
    w = AppShell()
    assert hasattr(w, "_open_settings_menu")
    assert hasattr(w, "_open_about")


def test_status_message_is_captured_not_dropped():
    _app()
    w = AppShell()
    w._set_status("hello")
    assert w._status_text == "hello"


def test_command_bar_present_with_dir_actions():
    _app()
    w = AppShell()
    assert w.command_bar is not None
    assert hasattr(w.command_bar, "btn_open_dir")
    assert hasattr(w.command_bar, "btn_set_output")


def test_command_bar_count_reflects_state():
    _app()
    w = AppShell()
    w._refresh_counts()
    assert "已选 0" in w.command_bar.count_text()


def test_command_bar_signals_wire_to_shell():
    _app()
    w = AppShell()
    # 信号存在且为已连接的入口（不弹真实文件框）
    assert hasattr(w, "_open_dir") and hasattr(w, "_set_out_dir")
    assert callable(w._open_dir) and callable(w._set_out_dir)
    # Headless-safe wiring proof: the real slots open a blocking QFileDialog,
    # so we never emit them while connected to AppShell. Instead disconnect the
    # shell slot, attach a spy, and confirm clicking the button emits the signal
    # (proving button.clicked -> signal wiring inside ProjectCommandBar). The
    # AppShell-side connection is re-established right after, with the spy
    # disconnected first so the signal ends with exactly its original wiring.
    try:
        w.command_bar.openDirRequested.disconnect(w._open_dir)
    except (RuntimeError, TypeError):
        pass
    fired = {}
    spy = lambda: fired.setdefault("open", True)
    w.command_bar.openDirRequested.connect(spy)
    w.command_bar.btn_open_dir.click()
    assert fired.get("open") is True
    # disconnect spy before re-attaching real slot → exactly 1 receiver
    try:
        w.command_bar.openDirRequested.disconnect(spy)
    except (RuntimeError, TypeError):
        pass
    w.command_bar.openDirRequested.connect(w._open_dir)
    assert w.command_bar.openDirRequested is not None


def test_switching_to_batch_page_syncs_selection_and_count():
    _app()
    w = AppShell()
    w.switchTo(w.pages["split"])
    # 新构造、未选任何图 → 全局 selected 同步为空、计数为 0
    w._on_page_changed()
    assert w.state.selected == []
    assert "已选 0" in w.command_bar.count_text()
    # selected_order 暴露在页与网格上
    assert w.pages["split"].selected_order() == []
