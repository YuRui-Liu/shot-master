import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QWidget
from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor


def _app():
    return QApplication.instance() or QApplication([])


def _cfg(tmp_path):
    return type("C", (), {"soundtrack_workflow_id": "", "soundtrack_seeds_count": 2,
                          "soundtrack_output_dir": "", "video_output_dir": str(tmp_path),
                          "soundtrack_crossfade": 0.5, "accent_big_threshold": 0.7,
                          "accent_snap_window": 0.6})()


def _task():
    return {"id": "t1", "name": "EP01", "mp4": "/x/ep1.mp4",
            "style": "末日废土", "output_dir": "", "status": "空闲", "output": ""}


def test_editor_is_qwidget_with_three_tabs(tmp_path):
    _app()
    ed = SoundtrackEditor(_task(), _cfg(tmp_path), tmp_path)
    assert isinstance(ed, QWidget)
    assert ed.tabs.count() == 3
    assert ed.style_edit.toPlainText() == "末日废土"


def test_editor_has_no_closed_signal():
    # widget 不需要 closed 信号 / closeEvent；浮出由 DetachedEditorWindow 承载
    assert not hasattr(SoundtrackEditor, "closed")


def test_to_payload_reads_widgets(tmp_path):
    _app()
    ed = SoundtrackEditor(_task(), _cfg(tmp_path), tmp_path)
    ed.mp4_edit.setText("/y/ep2.mp4")
    ed.style_edit.setPlainText("赛博霓虹")
    ed.out_edit.setText("/out/dir")
    p = ed.to_payload()
    assert p == {"mp4": "/y/ep2.mp4", "style": "赛博霓虹", "output_dir": "/out/dir"}


def test_output_base_falls_back(tmp_path):
    _app()
    ed = SoundtrackEditor(_task(), _cfg(tmp_path), tmp_path)
    assert "soundtrack" in str(ed._resolve_output_base())


def test_export_guard_no_mp4_does_not_crash(tmp_path, monkeypatch):
    _app()
    import drama_shot_master.ui.widgets.soundtrack_editor as m
    ed = SoundtrackEditor({"id": "t1", "name": "EP1", "mp4": "", "style": ""},
                          _cfg(tmp_path), tmp_path)
    monkeypatch.setattr(m.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(m.QMessageBox, "information", staticmethod(lambda *a, **k: None))
    assert hasattr(ed, "btn_export")
    ed._on_export()        # 无 mp4 → 走校验提示并 return，不崩


def test_preview_button_toggles_with_output(tmp_path, monkeypatch):
    _app()
    import drama_shot_master.ui.widgets.soundtrack_editor as m
    ed = SoundtrackEditor({"id": "t1", "name": "EP1", "mp4": "", "style": ""},
                          _cfg(tmp_path), tmp_path)
    assert ed.btn_preview.isEnabled() is False
    opened = []
    monkeypatch.setattr(m.QDesktopServices, "openUrl", lambda url: opened.append(url))
    fake = tmp_path / "clip_scored.mp4"; fake.write_bytes(b"x")
    ed._session = type("S", (), {"output": str(fake)})()
    ed._update_preview_enabled()
    assert ed.btn_preview.isEnabled() is True
    ed._on_preview()
    assert opened


def test_session_mount_does_not_crash(tmp_path, monkeypatch):
    # monkeypatch facade.load_session 返回空 session（segments/accent_points 空）
    # → _try_load_existing → _mount_session_tabs 构造 review/accent 不崩
    _app()
    import drama_shot_master.ui.widgets.soundtrack_editor as m
    stub = type("Sess", (), {"segments": [], "accent_points": [],
                             "source_mp4": "", "output": None})()
    monkeypatch.setattr(m, "_load_session_safe", lambda wd: stub, raising=False)
    # 直接验证 _mount_session_tabs 不崩（绕开 facade import 细节）
    ed = SoundtrackEditor(_task(), _cfg(tmp_path), tmp_path)
    ed._session = stub
    ed._mount_session_tabs()
    assert ed._review is not None and ed._accent is not None
