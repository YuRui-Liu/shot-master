"""主题系统 smoke：apply_theme 切换、token 注入、repolish。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from drama_shot_master.ui import theme


def _app():
    return QApplication.instance() or QApplication([])


def test_apply_theme_dark_injects_dark_bg():
    app = _app()
    theme.apply_theme(app, "dark")
    css = app.styleSheet()
    assert "#1e1f22" in css        # bg token expanded
    assert "{bg}" not in css      # no unresolved placeholder


def test_apply_theme_unknown_falls_back_to_dark():
    app = _app()
    theme.apply_theme(app, "nonsense-name")
    assert "#1e1f22" in app.styleSheet()


def test_current_theme_reads_cfg_default_dark():
    cfg = type("C", (), {})()
    assert theme.current_theme(cfg) == "dark"


def test_current_theme_reads_cfg_value():
    cfg = type("C", (), {"theme": "light"})()
    assert theme.current_theme(cfg) == "light"


def test_apply_theme_light_swaps_palette():
    app = _app()
    theme.apply_theme(app, "dark")
    dark_css = app.styleSheet()
    assert "#1e1f22" in dark_css and "#fafafa" not in dark_css
    theme.apply_theme(app, "light")
    light_css = app.styleSheet()
    assert "#fafafa" in light_css
    assert "#1e1f22" not in light_css
    # 切回 dark 也要稳
    theme.apply_theme(app, "dark")
    assert "#1e1f22" in app.styleSheet()
