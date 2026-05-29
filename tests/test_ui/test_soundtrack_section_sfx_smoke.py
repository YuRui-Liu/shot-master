"""SoundtrackSection 6 个 sfx_* 控件 + load/save 往返。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from drama_shot_master.config import Config
from drama_shot_master.ui.widgets.settings_sections.soundtrack_section \
    import SoundtrackSection


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_section_has_all_sfx_controls(app):
    section = SoundtrackSection(Config())
    for attr in ["sfx_workflow_edit", "sfx_frames_combo", "sfx_concurrency_spin",
                 "sfx_volume_spin", "sfx_ducking_spin", "sfx_seeds_spin"]:
        assert hasattr(section, attr), f"缺 {attr}"


def test_load_from_populates_sfx_controls(app):
    cfg = Config()
    cfg.sfx_workflow_id = "wf-xyz"
    cfg.sfx_plan_frames_per_shot = 5
    cfg.sfx_max_concurrency = 6
    cfg.sfx_default_volume = 1.1
    cfg.sfx_ducking_db = -9.0
    cfg.sfx_seeds_count = 3
    section = SoundtrackSection(cfg)
    section.load_from(cfg)
    assert section.sfx_workflow_edit.text() == "wf-xyz"
    assert section.sfx_frames_combo.currentText() == "5"
    assert section.sfx_concurrency_spin.value() == 6
    assert abs(section.sfx_volume_spin.value() - 1.1) < 1e-6
    assert abs(section.sfx_ducking_spin.value() - (-9.0)) < 1e-6
    assert section.sfx_seeds_spin.value() == 3


def test_save_to_writes_sfx_fields(app):
    cfg = Config()
    section = SoundtrackSection(cfg)
    section.sfx_workflow_edit.setText("wf-new")
    section.sfx_frames_combo.setCurrentText("5")
    section.sfx_concurrency_spin.setValue(4)
    section.sfx_volume_spin.setValue(0.9)
    section.sfx_ducking_spin.setValue(-8.0)
    section.sfx_seeds_spin.setValue(2)
    section.save_to(cfg)
    assert cfg.sfx_workflow_id == "wf-new"
    assert cfg.sfx_plan_frames_per_shot == 5
    assert cfg.sfx_max_concurrency == 4
    assert abs(cfg.sfx_default_volume - 0.9) < 1e-6
    assert abs(cfg.sfx_ducking_db - (-8.0)) < 1e-6
    assert cfg.sfx_seeds_count == 2
