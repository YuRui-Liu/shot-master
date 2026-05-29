import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter.script_page import ScriptPage


def _app():
    return QApplication.instance() or QApplication([])


class _StubClient:
    pass


def test_set_project_none_disables_buttons():
    _app()
    p = ScriptPage(_StubClient())
    p.set_project(None)
    assert p._gen_btn.isEnabled() is False
    assert p._save_btn.isEnabled() is False
    assert p._advance_btn.isEnabled() is False


def test_loads_existing_script_md(tmp_path):
    _app()
    (tmp_path / "剧本.md").write_text("# 剧本信息\n标题: 测试\n## 镜头 01\n画面: x\n",
                                       encoding="utf-8")
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    assert "镜头 01" in p._editor.toPlainText()
    assert p._state == "done"
    assert p._advance_btn.isEnabled() is True


def test_idle_when_no_script(tmp_path):
    _app()
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    assert p._state == "idle"
    assert p._editor.toPlainText() == ""
    assert p._advance_btn.isEnabled() is False


def test_edit_then_save_button_enables(tmp_path):
    _app()
    (tmp_path / "剧本.md").write_text("orig\n", encoding="utf-8")
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    assert p._save_btn.isEnabled() is False
    p._editor.setPlainText("edited\n")
    assert p._save_btn.isEnabled() is True


def test_save_writes_disk_and_clears_dirty(tmp_path):
    _app()
    (tmp_path / "剧本.md").write_text("orig\n", encoding="utf-8")
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    p._editor.setPlainText("edited content\n")
    p._on_save_clicked()
    assert (tmp_path / "剧本.md").read_text(encoding="utf-8") == "edited content\n"
    assert p._save_btn.isEnabled() is False


def test_try_release_blocks_when_dirty(tmp_path, monkeypatch):
    _app()
    (tmp_path / "剧本.md").write_text("orig\n", encoding="utf-8")
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    p._editor.setPlainText("edited\n")
    import drama_shot_master.ui.widgets.screenwriter.script_page as m
    monkeypatch.setattr(m.QMessageBox, "question",
                         staticmethod(lambda *a, **k: m.QMessageBox.Cancel))
    assert p.try_release() is False
    # 用户选 Discard：放行
    monkeypatch.setattr(m.QMessageBox, "question",
                         staticmethod(lambda *a, **k: m.QMessageBox.Discard))
    assert p.try_release() is True


def test_upstream_check_blocks_generate(tmp_path, monkeypatch):
    _app()
    # 没有 idea.json → 点生成应该弹 warning 而不发流
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    import drama_shot_master.ui.widgets.screenwriter.script_page as m
    called = []
    monkeypatch.setattr(m.QMessageBox, "warning",
                         staticmethod(lambda *a, **k: called.append(True)))
    p._on_generate_clicked()
    assert called
    assert p._state == "idle"   # 没启流


def test_sse_delta_appends_to_editor(tmp_path):
    _app()
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    # 直接调 _on_sse_event 模拟流式 delta
    p._on_sse_event("delta", {"text": "你好"})
    p._on_sse_event("delta", {"text": "世界"})
    assert "你好世界" in p._editor.toPlainText()
