import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.settings_sections.runninghub_section import RunningHubSection
from drama_shot_master.ui.widgets.settings_sections.translation_section import TranslationSection
from drama_shot_master.ui.widgets.settings_sections.refine_section import RefineSection
from drama_shot_master.ui.widgets.settings_sections.imggen_section import ImgGenSection
from drama_shot_master.ui.widgets.settings_sections.dub_section import DubSection
from drama_shot_master.ui.widgets.settings_sections.soundtrack_section import SoundtrackSection


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
    assert TranslationSection.category == "其他"      # 翻译非平台核心


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
    # Refine 现在共用 LLM 平台的 base_url/api_key（同步写回扁平字段供 prompt_refiner 消费）
    cfg = _cfg(
        refine_provider="deepseek",
        refine_base_url="",
        refine_api_key="",
        refine_model="deepseek-chat",
        refine_meta_prompt_path="",
        llm_providers={"deepseek": {"base_url": "https://api.deepseek.com",
                                     "api_key": "dummy-key"}},
    )
    sec = RefineSection(cfg)
    # 切到 doubao
    idx = sec.provider_combo.findData("doubao")
    sec.provider_combo.setCurrentIndex(idx)
    sec.model_edit.setText("doubao-1-5-pro-32k-241215")
    # 添加 doubao 平台配置
    cfg.llm_providers["doubao"] = {"base_url": "https://ark.cn-beijing.volces.com/api/v3",
                                    "api_key": "ark-key"}
    sec.save_to(cfg)
    assert cfg.refine_provider == "doubao"
    assert cfg.refine_model == "doubao-1-5-pro-32k-241215"
    # 共用映射：save_to 把 LLM 平台的 url+key 同步回扁平字段
    assert cfg.refine_base_url == "https://ark.cn-beijing.volces.com/api/v3"
    assert cfg.refine_api_key == "ark-key"


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


# ── SoundtrackSection ─────────────────────────────────────────────────────────

def test_soundtrack_section_class_metadata():
    assert SoundtrackSection.title == "配乐"
    assert SoundtrackSection.category == "生成功能"


def test_soundtrack_section_load_save_roundtrip():
    _app()
    cfg = _cfg(
        soundtrack_workflow_id="wf-ace-1",
        soundtrack_output_dir="/tmp/soundtrack",
        soundtrack_seeds_count=2,
        soundtrack_crossfade=0.5,
        accent_big_threshold=0.7,
        accent_snap_window=0.6,
    )
    sec = SoundtrackSection(cfg)
    assert sec.workflow_edit.text() == "wf-ace-1"
    sec.workflow_edit.setText("wf-ace-2")
    sec.seeds_spin.setValue(3)
    sec.save_to(cfg)
    assert cfg.soundtrack_workflow_id == "wf-ace-2"
    assert cfg.soundtrack_seeds_count == 3
    assert cfg.accent_big_threshold == 0.7


# ── ThemeSection ──────────────────────────────────────────────────────────────

def test_theme_section_metadata():
    from drama_shot_master.ui.widgets.settings_sections.theme_section import ThemeSection
    assert ThemeSection.title == "主题"
    assert ThemeSection.category == "外观"


def test_theme_section_combo_switch_calls_apply(monkeypatch):
    _app()
    from drama_shot_master.ui.widgets.settings_sections.theme_section import ThemeSection
    from drama_shot_master.ui import theme as theme_mod
    called = []
    monkeypatch.setattr(theme_mod, "apply_theme", lambda app, name: called.append(("apply", name)))
    monkeypatch.setattr(theme_mod, "apply_titlebar", lambda w, name: called.append(("titlebar", name)))
    cfg = _cfg(theme="dark")
    persisted = []
    cfg.update_settings = lambda **kw: persisted.append(kw)
    from PySide6.QtWidgets import QApplication
    sec = ThemeSection(QApplication.instance(), cfg)
    sec.combo.setCurrentText("浅色")
    assert ("apply", "light") in called
    assert any(k.get("theme") == "light" for k in persisted)


def test_screenwriter_section_grid_default_roundtrip(tmp_path):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from drama_shot_master.config import load_config
    from drama_shot_master.ui.widgets.settings_sections.screenwriter_section import ScreenwriterSection
    cfg = load_config(env_path=tmp_path / ".env", settings_path=tmp_path / "settings.json")
    sec = ScreenwriterSection(cfg)
    # 默认四宫格被选中
    assert sec.grid_combo.currentData() == "4"
    # 改为九宫格 → save → cfg 生效
    sec.grid_combo.setCurrentIndex(sec.grid_combo.findData("9"))
    sec.save_to(cfg)
    assert cfg.prompts_default_grid == "9"
