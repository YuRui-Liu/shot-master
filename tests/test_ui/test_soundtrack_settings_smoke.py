import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.dialogs.soundtrack_settings_dialog import (
    SoundtrackSettingsDialog)


def _app():
    return QApplication.instance() or QApplication([])


class _Cfg:
    soundtrack_workflow_id = "wf-old"
    soundtrack_output_dir = "/x/out"
    soundtrack_seeds_count = 2
    soundtrack_crossfade = 0.5
    accent_big_threshold = 0.7
    accent_snap_window = 0.6
    def update_settings(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def test_dialog_loads_and_saves():
    _app()
    cfg = _Cfg()
    dlg = SoundtrackSettingsDialog(cfg)
    assert dlg.workflow_edit.text() == "wf-old"
    assert dlg.seeds_spin.value() == 2
    dlg.workflow_edit.setText("wf-new")
    dlg.seeds_spin.setValue(3)
    dlg.accept()
    assert cfg.soundtrack_workflow_id == "wf-new"
    assert cfg.soundtrack_seeds_count == 3


def test_dialog_loads_and_saves_accent_fields():
    _app()
    cfg = _Cfg()
    dlg = SoundtrackSettingsDialog(cfg)
    assert abs(dlg.big_thresh_spin.value() - 0.7) < 1e-6
    assert abs(dlg.snap_window_spin.value() - 0.6) < 1e-6
    dlg.big_thresh_spin.setValue(0.5)
    dlg.snap_window_spin.setValue(1.0)
    dlg.accept()
    assert abs(cfg.accent_big_threshold - 0.5) < 1e-6
    assert abs(cfg.accent_snap_window - 1.0) < 1e-6
