import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.theme import init_fluent_theme, THEME_ACCENT


def test_init_fluent_theme_sets_blue_accent():
    app = QApplication.instance() or QApplication([])
    # 不应抛异常；返回当前主题色 QColor，name() 等于配置的冷蓝
    color = init_fluent_theme(app)
    assert color.name().lower() == THEME_ACCENT.lower()
