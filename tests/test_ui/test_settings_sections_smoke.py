import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.settings_sections.runninghub_section import RunningHubSection
from drama_shot_master.ui.widgets.settings_sections.translation_section import TranslationSection


def _app():
    return QApplication.instance() or QApplication([])


def _cfg(**kw):
    base = {
        "runninghub_api_key": "k1",
        "runninghub_base_url": "https://www.runninghub.cn",
        "video_output_dir": "",
        "workflow_ids": {},
        "runninghub_workflow_id": "",
        "runninghub_template_path": "",
        "deeplx_url": "",
    }
    base.update(kw)
    c = type("C", (), base)()
    c.update_settings = lambda **upd: [setattr(c, k, v) for k, v in upd.items()]
    return c


def test_runninghub_section_class_metadata():
    assert RunningHubSection.title == "RunningHub"
    assert RunningHubSection.category == "平台核心"


def test_runninghub_section_load_save_roundtrip():
    _app()
    cfg = _cfg(
        runninghub_api_key="k1",
        runninghub_base_url="https://example.com",
        video_output_dir="/tmp/out",
        workflow_ids={"director": "wf-director"},
        runninghub_workflow_id="",
        runninghub_template_path="",
    )
    sec = RunningHubSection(cfg)
    # Change some fields
    sec.api_key_edit.setText("k2")
    sec.workflow_id_edits["director"].setText("wf-new")
    sec.save_to(cfg)
    assert cfg.runninghub_api_key == "k2"
    assert cfg.workflow_ids["director"] == "wf-new"
    assert cfg.runninghub_workflow_id == "wf-new"  # synced write


def test_runninghub_section_validate_default_ok():
    _app()
    cfg = _cfg(workflow_ids={"director": "wf-123"})
    sec = RunningHubSection(cfg)
    ok, _ = sec.validate()
    assert ok is True


def test_runninghub_section_validate_requires_director_workflow_id():
    _app()
    cfg = _cfg(
        runninghub_api_key="k",
        runninghub_base_url="",
        video_output_dir="",
        workflow_ids={},
        runninghub_workflow_id="",
        runninghub_template_path="",
    )
    sec = RunningHubSection(cfg)
    # Leave director empty
    sec.workflow_id_edits["director"].setText("")
    ok, why = sec.validate()
    assert ok is False
    assert "director" in why.lower() or "导演台" in why


# ── TranslationSection ────────────────────────────────────────────────────────

def test_translation_section_class_metadata():
    assert TranslationSection.title == "翻译"
    assert TranslationSection.category == "平台核心"


def test_translation_section_load_save_roundtrip():
    _app()
    cfg = _cfg(deeplx_url="https://api.deeplx.org/translate")
    sec = TranslationSection(cfg)
    assert sec.url_edit.text() == "https://api.deeplx.org/translate"
    sec.url_edit.setText("http://localhost:1188/translate")
    sec.save_to(cfg)
    assert cfg.deeplx_url == "http://localhost:1188/translate"
