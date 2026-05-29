"""Offscreen smoke for TranslationSection (provider radio + stack + save/load)."""
from __future__ import annotations

import os
import types

import pytest
from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.settings_sections.translation_section \
    import TranslationSection


@pytest.fixture(scope="module")
def app():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    a = QApplication.instance() or QApplication([])
    yield a


def _cfg(**kwargs):
    defaults = dict(
        current_translator="",
        tencent_translator_secret_id="",
        tencent_translator_secret_key="",
        tencent_translator_region="ap-beijing",
        tencent_translator_project_id=0,
        deeplx_url="",
        # update_settings spy
        _updates=[],
    )
    defaults.update(kwargs)
    ns = types.SimpleNamespace(**defaults)
    def _update(**fields):
        ns._updates.append(fields)
        for k, v in fields.items():
            setattr(ns, k, v)
    ns.update_settings = _update
    return ns


def test_default_loads_tencent_radio(app):
    cfg = _cfg()
    sec = TranslationSection(cfg)
    # _post_load_migrate not run here (using bare _cfg); empty current_translator
    # falls through to "tencent" in load_from's default branch.
    assert sec.rb_tencent.isChecked()
    assert sec.stack.currentIndex() == 0


def test_loads_deeplx_when_cfg_says_deeplx(app):
    cfg = _cfg(current_translator="deeplx",
               deeplx_url="http://example/translate")
    sec = TranslationSection(cfg)
    assert sec.rb_deeplx.isChecked()
    assert sec.stack.currentIndex() == 1
    assert sec.dl_url.text() == "http://example/translate"


def test_clicking_deeplx_switches_stack(app):
    cfg = _cfg(current_translator="tencent")
    sec = TranslationSection(cfg)
    sec.rb_deeplx.setChecked(True)
    assert sec.stack.currentIndex() == 1


def test_save_to_updates_cfg_and_clears_cache(app, monkeypatch):
    cleared = []
    monkeypatch.setattr(
        "drama_shot_master.providers.translator.clear_cache",
        lambda: cleared.append(True))
    cfg = _cfg(current_translator="tencent")
    sec = TranslationSection(cfg)
    sec.tc_sid.setText("new-sid")
    sec.tc_skey.setText("new-skey")
    sec.tc_region.setCurrentText("ap-shanghai")
    sec.tc_pid.setValue(7)
    sec.save_to(cfg)
    assert cfg.tencent_translator_secret_id == "new-sid"
    assert cfg.tencent_translator_secret_key == "new-skey"
    assert cfg.tencent_translator_region == "ap-shanghai"
    assert cfg.tencent_translator_project_id == 7
    assert cleared == [True]


def test_validate_tencent_missing_creds_fails(app):
    cfg = _cfg(current_translator="tencent")
    sec = TranslationSection(cfg)
    sec.tc_sid.setText("")
    sec.tc_skey.setText("")
    ok, msg = sec.validate()
    assert ok is False
    assert "Secret" in msg


def test_validate_deeplx_missing_url_fails(app):
    cfg = _cfg(current_translator="deeplx", deeplx_url="")
    sec = TranslationSection(cfg)
    sec.rb_deeplx.setChecked(True)
    sec.dl_url.setText("")
    ok, msg = sec.validate()
    assert ok is False
    assert "URL" in msg
