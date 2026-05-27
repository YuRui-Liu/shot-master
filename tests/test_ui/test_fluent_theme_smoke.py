import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.theme import init_fluent_theme, THEME_ACCENT


def test_init_fluent_theme_sets_blue_accent():
    app = QApplication.instance() or QApplication([])
    color = init_fluent_theme(app)
    # 返回请求的主题色
    assert color.name().lower() == THEME_ACCENT.lower()
    # 且确实驱动了 Fluent 主题系统：深色生效 + 主题色为有效色
    from qfluentwidgets import isDarkTheme, themeColor
    assert isDarkTheme() is True
    assert themeColor().isValid()
