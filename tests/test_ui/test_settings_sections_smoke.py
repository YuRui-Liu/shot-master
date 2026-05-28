import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.settings_sections.runninghub_section import RunningHubSection
from drama_shot_master.ui.widgets.settings_sections.translation_section import TranslationSection
from drama_shot_master.ui.widgets.settings_sections.refine_section import RefineSection
from drama_shot_master.ui.widgets.settings_sections.imggen_section import ImgGenSection
from drama_shot_master.ui.widgets.settings_sections.dub_section import DubSection


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


# ── RefineSection ─────────────────────────────────────────────────────────────

def test_refine_section_class_metadata():
    assert RefineSection.title == "提示词优化"
    assert RefineSection.category == "辅助"


def test_refine_section_load_save_roundtrip():
    _app()
    cfg = _cfg(
        refine_provider_preset="Ollama (本地)",
        refine_base_url="http://localhost:11434/v1",
        refine_api_key="",
        refine_model="qwen2.5-vl",
        refine_meta_prompt_path="",
    )
    sec = RefineSection(cfg)
    assert sec.base_url_edit.text() == "http://localhost:11434/v1"
    sec.base_url_edit.setText("http://localhost:11434/v1")
    sec.model_combo.setCurrentText("qwen2.5-vl:7b")
    sec.save_to(cfg)
    assert cfg.refine_base_url == "http://localhost:11434/v1"
    assert cfg.refine_model == "qwen2.5-vl:7b"


# ── ImgGenSection ─────────────────────────────────────────────────────────────

def test_imggen_section_class_metadata():
    assert ImgGenSection.title == "出图"
    assert ImgGenSection.category == "生成功能"


def test_imggen_section_load_save_roundtrip():
    _app()
    cfg = _cfg(
        imggen_provider="doubao",
        imggen_base_url="https://ark.cn-beijing.volces.com/api/v3",
        imggen_model="seedream-3-0-t2i-250415",
        imggen_api_key="key1",
        imggen_output_dir="/tmp/imgs",
        imggen_watermark=False,
        api_keys={},
    )
    sec = ImgGenSection(cfg)
    assert sec.model.text() == "seedream-3-0-t2i-250415"
    sec.model.setText("seedream-new")
    sec.save_to(cfg)
    assert cfg.imggen_model == "seedream-new"
    assert cfg.imggen_output_dir == "/tmp/imgs"


# ── DubSection ────────────────────────────────────────────────────────────────

def test_dub_section_class_metadata():
    assert DubSection.title == "配音"
    assert DubSection.category == "生成功能"


def test_dub_section_load_save_roundtrip():
    _app()
    cfg = _cfg(
        dub_workflow_ids={"voice_design": "wf-design-1", "voice_clone": "wf-clone-1"},
        dub_output_dir="/tmp/dub",
    )
    sec = DubSection(cfg)
    assert sec.wf_design.text() == "wf-design-1"
    sec.wf_clone.setText("wf-clone-new")
    sec.save_to(cfg)
    assert cfg.dub_workflow_ids["voice_clone"] == "wf-clone-new"
    assert cfg.dub_output_dir == "/tmp/dub"
