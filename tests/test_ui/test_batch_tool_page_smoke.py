import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.config import load_config
from drama_shot_master.ui.state import AppState
from drama_shot_master.ui.panels.trim_panel import TrimPanel
from drama_shot_master.ui.pages.batch_tool_page import BatchToolPage


def _app():
    return QApplication.instance() or QApplication([])


def test_page_exposes_grid_panel_and_exec_button():
    _app()
    state, cfg = AppState(), load_config()
    panel = TrimPanel(state, cfg)
    page = BatchToolPage(panel, state, cfg)
    assert page.thumb is not None          # 缩略图网格
    assert page.panel is panel             # 内嵌的批处理 panel
    assert hasattr(page, "btn_exec")       # 执行按钮
    assert hasattr(page, "btn_preview")    # 预览按钮


def test_exec_button_disabled_when_panel_invalid():
    _app()
    state, cfg = AppState(), load_config()
    page = BatchToolPage(TrimPanel(state, cfg), state, cfg)
    # 未选目录/图片 → 不可执行
    ok, _why = page.panel.validate()
    assert page.btn_exec.isEnabled() == ok
