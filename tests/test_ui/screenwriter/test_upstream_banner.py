"""_UpstreamBanner 单元测试。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter._upstream_banner import _UpstreamBanner


def _app():
    return QApplication.instance() or QApplication([])


def test_banner_hidden_initially():
    _app()
    b = _UpstreamBanner()
    assert b.isHidden() is True


def test_show_missing_sets_text_and_visible():
    _app()
    b = _UpstreamBanner()
    b.show_missing(stage_name="剧本", expected_file="剧本.md")
    assert not b.isHidden()
    assert "剧本" in b.text()
    assert "剧本.md" in b.text()


def test_hide_after_show():
    _app()
    b = _UpstreamBanner()
    b.show_missing(stage_name="分镜", expected_file="分镜.json")
    b.hide_banner()
    assert b.isHidden() is True


def test_text_method_returns_label_text():
    _app()
    b = _UpstreamBanner()
    b.show_missing(stage_name="提示词", expected_file="prompts/")
    # text() 应返非空
    assert len(b.text()) > 0
