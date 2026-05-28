import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.settings_sections.runninghub_section import RunningHubSection


def _app():
    return QApplication.instance() or QApplication([])


def _cfg(**kw):
    # Real cfg field names: runninghub_api_key, runninghub_base_url
    base = {"runninghub_api_key": "k1", "runninghub_base_url": "https://www.runninghub.cn"}
    base.update(kw)
    return type("C", (), base)()


def test_runninghub_section_class_metadata():
    assert RunningHubSection.title == "RunningHub"
    assert RunningHubSection.category == "平台核心"


def test_runninghub_section_load_save_roundtrip():
    _app()
    cfg = _cfg()
    sec = RunningHubSection(cfg)
    sec.load_from(cfg)
    sec.api_key_edit.setText("k2")
    sec.save_to(cfg)
    assert cfg.runninghub_api_key == "k2"


def test_runninghub_section_validate_default_ok():
    _app()
    sec = RunningHubSection(_cfg())
    ok, _ = sec.validate()
    assert ok is True
