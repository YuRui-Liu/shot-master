import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.settings_sections.screenwriter_section import (
    ScreenwriterSection,
)
from screenwriter_agent.templates import template_loader as tl


def _app():
    return QApplication.instance() or QApplication([])


class _StubCfg:
    def __init__(self):
        self.screenwriter_project_root = ""
        self.screenwriter_stage_assignments = {}
        self.screenwriter_models = {}
        self._saved = {}

    def update_settings(self, **kw):
        self._saved.update(kw)


def test_section_shows_builtin_when_no_global(tmp_path, monkeypatch):
    _app()
    monkeypatch.setattr(tl, "GLOBAL_TEMPLATE_DIR", tmp_path / "global")
    s = ScreenwriterSection()
    s.load_from(_StubCfg())
    # 创意 editor 文本应该非空（来自 builtin）
    assert len(s._template_editors["ideate"].toPlainText()) > 0


def test_save_writes_global_when_user_changed(tmp_path, monkeypatch):
    _app()
    monkeypatch.setattr(tl, "GLOBAL_TEMPLATE_DIR", tmp_path / "global")
    s = ScreenwriterSection()
    s.load_from(_StubCfg())
    s._template_editors["ideate"].setPlainText("MY CUSTOM IDEATE")
    s.save_to(_StubCfg())
    p = tmp_path / "global" / "ideate.md"
    assert p.is_file()
    assert p.read_text(encoding="utf-8") == "MY CUSTOM IDEATE"


def test_save_skips_unchanged(tmp_path, monkeypatch):
    _app()
    monkeypatch.setattr(tl, "GLOBAL_TEMPLATE_DIR", tmp_path / "global")
    s = ScreenwriterSection()
    s.load_from(_StubCfg())
    s.save_to(_StubCfg())  # 没改任何东西
    # global 目录里不应有 ideate.md（因为没动）
    assert not (tmp_path / "global" / "ideate.md").exists()
