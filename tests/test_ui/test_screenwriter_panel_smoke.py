import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.panels.screenwriter_panel import ScreenwriterPanel


def _app():
    return QApplication.instance() or QApplication([])


def test_panel_constructs(tmp_path):
    _app()
    cfg = type("C", (), {"screenwriter_project_root": str(tmp_path),
                         "screenwriter_models": {}})()
    panel = ScreenwriterPanel(cfg=cfg, client=None, lifecycle=None)
    # 必备控件
    assert hasattr(panel, "table")
    assert hasattr(panel, "btn_new")
    assert hasattr(panel, "btn_open")
    assert hasattr(panel, "btn_del")
    assert hasattr(panel, "wizard")          # QStackedWidget
    assert panel.wizard.count() == 4         # 4 阶段


def test_panel_table_cols(tmp_path):
    _app()
    cfg = type("C", (), {"screenwriter_project_root": str(tmp_path),
                         "screenwriter_models": {}})()
    panel = ScreenwriterPanel(cfg=cfg, client=None, lifecycle=None)
    hdr = panel.table.horizontalHeaderItem
    assert hdr(0).text() == "名称"
    assert hdr(1).text() == "状态"
