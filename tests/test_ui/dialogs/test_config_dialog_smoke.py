import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_config_dialog_construct_and_field_roundtrip(app):
    from drama_shot_master.ui.dialogs.config_dialog import ConfigDialog
    initial = {"mp4": "/a.mp4", "style": "末日", "output_dir": "/out"}
    dlg = ConfigDialog(initial)
    assert dlg.mp4_edit.text() == "/a.mp4"
    assert dlg.style_edit.toPlainText() == "末日"
    assert dlg.out_edit.text() == "/out"
    dlg.mp4_edit.setText("/b.mp4")
    dlg.style_edit.setPlainText("古风")
    dlg.out_edit.setText("/out2")
    payload = dlg.to_payload()
    assert payload == {"mp4": "/b.mp4", "style": "古风", "output_dir": "/out2"}


def test_config_dialog_browse_mp4_does_not_crash(app, monkeypatch):
    from drama_shot_master.ui.dialogs.config_dialog import ConfigDialog
    dlg = ConfigDialog({"mp4": "", "style": "", "output_dir": ""})
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        lambda *a, **k: ("/picked.mp4", "*"))
    dlg._browse_mp4()
    assert dlg.mp4_edit.text() == "/picked.mp4"


def test_config_dialog_browse_output_dir_does_not_crash(app, monkeypatch):
    from drama_shot_master.ui.dialogs.config_dialog import ConfigDialog
    dlg = ConfigDialog({"mp4": "", "style": "", "output_dir": ""})
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        lambda *a, **k: "/picked_dir")
    dlg._browse_out()
    assert dlg.out_edit.text() == "/picked_dir"
