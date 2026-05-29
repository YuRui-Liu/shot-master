"""SoundtrackSection 6 个新控件存在 + load_from/save_to cfg 往返。"""
import pytest
from PySide6.QtWidgets import QApplication

from drama_shot_master.config import Config
from drama_shot_master.ui.widgets.settings_sections.soundtrack_section \
    import SoundtrackSection


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_section_has_all_six_new_controls(app):
    cfg = Config()
    section = SoundtrackSection(cfg)
    for attr in ["frames_combo", "refine_max_spin", "refine_thresh_spin",
                 "stretch_spin", "concurrency_spin",
                 "w_health", "w_headroom", "w_beat"]:
        assert hasattr(section, attr), f"缺控件 {attr}"


def test_load_from_populates_controls(app):
    cfg = Config()
    cfg.refine_frames_per_shot = 5
    cfg.refine_max_segments = 8
    cfg.refine_merge_threshold = 0.30
    cfg.accent_max_stretch = 0.20
    cfg.soundtrack_max_concurrency = 6
    cfg.soundtrack_score_weights = {"health": 0.7, "headroom": 0.2, "beat": 0.1}
    section = SoundtrackSection(cfg)
    section.load_from(cfg)
    assert section.frames_combo.currentText() == "5"
    assert section.refine_max_spin.value() == 8
    assert abs(section.refine_thresh_spin.value() - 0.30) < 1e-6
    assert abs(section.stretch_spin.value() - 0.20) < 1e-6
    assert section.concurrency_spin.value() == 6
    assert abs(section.w_health.value() - 0.7) < 1e-6
    assert abs(section.w_headroom.value() - 0.2) < 1e-6
    assert abs(section.w_beat.value() - 0.1) < 1e-6


def test_save_to_writes_back_to_cfg(app):
    """save_to 是 UnifiedSettingsDialog 真正调用的持久化入口；6 个新字段
    必须走这一条路径才能在设置对话框关闭时落盘。"""
    cfg = Config()
    section = SoundtrackSection(cfg)
    section.frames_combo.setCurrentText("5")
    section.refine_max_spin.setValue(7)
    section.refine_thresh_spin.setValue(0.40)
    section.stretch_spin.setValue(0.15)
    section.concurrency_spin.setValue(4)
    section.w_health.setValue(0.6)
    section.w_headroom.setValue(0.3)
    section.w_beat.setValue(0.1)
    section.save_to(cfg)
    assert cfg.refine_frames_per_shot == 5
    assert cfg.refine_max_segments == 7
    assert abs(cfg.refine_merge_threshold - 0.40) < 1e-6
    assert abs(cfg.accent_max_stretch - 0.15) < 1e-6
    assert cfg.soundtrack_max_concurrency == 4
    assert cfg.soundtrack_score_weights == {
        "health": 0.6, "headroom": 0.3, "beat": 0.1}
