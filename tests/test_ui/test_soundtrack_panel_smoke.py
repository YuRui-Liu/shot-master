import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.panels.soundtrack_panel import SoundtrackPanel


def _app():
    return QApplication.instance() or QApplication([])


def test_panel_constructs_and_lists_tasks():
    _app()
    opened = []
    panel = SoundtrackPanel(
        state=None,
        cfg=type("C", (), {"soundtrack_tasks": [
            {"id": "t1", "name": "EP01", "mp4": "/x/ep1.mp4",
             "style": "冷色调", "status": "空闲", "output": ""}]})(),
        open_window_cb=lambda t: opened.append(t),
        persist_cb=lambda: None,
    )
    assert panel.table.rowCount() == 1
    assert panel.select_mode() == "none"
    ok, _why = panel.validate()
    assert ok is False


def test_panel_rename_via_name_column():
    _app()
    persisted = []
    cfg = type("C", (), {"soundtrack_tasks": [
        {"id": "t1", "name": "旧名", "mp4": "/x/ep1.mp4",
         "style": "", "status": "空闲", "output": ""}]})()
    panel = SoundtrackPanel(
        state=None, cfg=cfg,
        open_window_cb=lambda t: None,
        persist_cb=lambda: persisted.append(1))
    # 模拟用户在名称列改名
    name_item = panel.table.item(0, 0)
    name_item.setText("新名字")          # 触发 itemChanged
    assert cfg.soundtrack_tasks[0]["name"] == "新名字"
    assert persisted                      # 落盘被调用


def test_panel_double_click_name_does_not_open():
    _app()
    opened = []
    cfg = type("C", (), {"soundtrack_tasks": [
        {"id": "t1", "name": "n", "mp4": "", "style": "",
         "status": "空闲", "output": ""}]})()
    panel = SoundtrackPanel(state=None, cfg=cfg,
                            open_window_cb=lambda t: opened.append(t),
                            persist_cb=lambda: None)
    panel.table.setCurrentCell(0, 0)      # 先选中行（否则 _on_open 弹模态框阻塞）
    panel._on_double_clicked(panel.table.item(0, 0))   # 名称列
    assert opened == []                   # 不打开（进内联编辑）
    panel._on_double_clicked(panel.table.item(0, 1))   # 其它列
    assert len(opened) == 1               # 打开
