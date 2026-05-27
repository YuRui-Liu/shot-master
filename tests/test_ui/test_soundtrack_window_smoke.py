import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.windows.soundtrack_task_window import (
    SoundtrackTaskWindow)


def _app():
    return QApplication.instance() or QApplication([])


class _Cfg:
    soundtrack_workflow_id = "wf-default"
    soundtrack_output_dir = ""
    soundtrack_seeds_count = 2
    soundtrack_crossfade = 0.5
    video_output_dir = "/tmp/vout"


def _task():
    return {"id": "t1", "name": "EP01", "mp4": "/x/ep1.mp4",
            "style": "末日废土", "output_dir": "", "status": "空闲", "output": ""}


def test_window_has_three_tabs():
    _app()
    win = SoundtrackTaskWindow(_task(), cfg=_Cfg(), work_root="/tmp/stk")
    assert win.tabs.count() == 3
    assert win.style_edit.toPlainText() == "末日废土"


def test_window_emits_closed_on_close():
    _app()
    win = SoundtrackTaskWindow(_task(), cfg=_Cfg(), work_root="/tmp/stk")
    seen = []
    win.closed.connect(seen.append)
    win.close()
    assert seen == ["t1"]


def test_output_dir_resolution_falls_back():
    _app()
    win = SoundtrackTaskWindow(_task(), cfg=_Cfg(), work_root="/tmp/stk")
    base = win._resolve_output_base()
    assert "soundtrack" in str(base)


def test_window_has_export_button(tmp_path, monkeypatch):
    import drama_shot_master.ui.windows.soundtrack_task_window as m
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from drama_shot_master.ui.windows.soundtrack_task_window import SoundtrackTaskWindow
    QApplication.instance() or QApplication([])
    cfg = type("C", (), {"soundtrack_workflow_id": "", "soundtrack_seeds_count": 2,
                         "soundtrack_output_dir": "", "video_output_dir": str(tmp_path),
                         "soundtrack_crossfade": 0.5, "accent_big_threshold": 0.7,
                         "accent_snap_window": 0.6})()
    w = SoundtrackTaskWindow({"id": "t1", "name": "EP1", "mp4": "", "style": ""},
                             cfg, tmp_path)
    monkeypatch.setattr(m.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(m.QMessageBox, "information", staticmethod(lambda *a, **k: None))
    assert hasattr(w, "btn_export")
    w._on_export()    # 无 mp4 → 走校验提示并 return,不崩


def test_preview_button_enabled_after_output(tmp_path, monkeypatch):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    import drama_shot_master.ui.windows.soundtrack_task_window as m
    QApplication.instance() or QApplication([])
    cfg = type("C", (), {"soundtrack_workflow_id": "", "soundtrack_seeds_count": 2,
                         "soundtrack_output_dir": "", "video_output_dir": str(tmp_path),
                         "soundtrack_crossfade": 0.5, "accent_big_threshold": 0.7,
                         "accent_snap_window": 0.6})()
    w = m.SoundtrackTaskWindow({"id": "t1", "name": "EP1", "mp4": "", "style": ""},
                               cfg, tmp_path)
    assert hasattr(w, "btn_preview")
    assert w.btn_preview.isEnabled() is False        # 还没出片 → 禁用
    opened = []
    monkeypatch.setattr(m.QDesktopServices, "openUrl", lambda url: opened.append(url))
    fake = tmp_path / "clip_scored.mp4"; fake.write_bytes(b"x")
    sess = type("S", (), {"output": str(fake)})()
    w._session = sess
    w._update_preview_enabled()
    assert w.btn_preview.isEnabled() is True
    w._on_preview()
    assert opened                                     # 调了系统打开
