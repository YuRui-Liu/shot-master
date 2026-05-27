import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.app_shell import AppShell
from drama_shot_master.ui.nav_config import FUNCS, PHASES, LABELS


def _app():
    return QApplication.instance() or QApplication([])


def _expected_breadcrumb(key):
    """Compute the breadcrumb the same way AppShell does, for the given key."""
    phase = next(t for t, keys in PHASES if key in keys)
    return f"{phase} › {LABELS[key]}"


def test_shell_constructs_and_registers_seven_pages():
    _app()
    w = AppShell()
    w.show()
    QApplication.instance().processEvents()
    assert len(w.pages) == len(FUNCS)


def test_shell_breadcrumb_reflects_initial_function():
    # After Task 5, _restore_state switches to cfg.last_active_function (falling
    # back to FUNCS[0] / "split" when unset or unknown). The breadcrumb therefore
    # reflects whichever page was restored — compute the expected value the same
    # way AppShell does instead of hard-coding "拆图".
    _app()
    w = AppShell()
    target = w.cfg.last_active_function
    key = target if target in w.pages else FUNCS[0][1]
    assert w.breadcrumb_text() == _expected_breadcrumb(key)


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
