import inspect
import drama_shot_master.main as m


def test_entry_imports_app_shell():
    src = inspect.getsource(m.main)
    assert "AppShell" in src
    assert "MainWindow" not in src
