import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.panels.soundtrack_panel import (
    SoundtrackPanel, _SoundtrackTaskView)


def _app():
    return QApplication.instance() or QApplication([])


def _cfg(tasks):
    return type("C", (), {"soundtrack_tasks": tasks})()


def test_panel_constructs_and_lists_tasks():
    _app()
    panel = SoundtrackPanel(
        state=None,
        cfg=_cfg([{"id": "t1", "name": "EP01", "mp4": "/x/ep1.mp4",
                   "style": "冷色调", "status": "空闲", "output": ""}]),
        open_window_cb=None, persist_cb=lambda: None)
    assert panel.table.rowCount() == 1
    assert panel.select_mode() == "none"
    ok, _why = panel.validate()
    assert ok is False


def test_selection_emits_task_view():
    _app()
    panel = SoundtrackPanel(
        state=None,
        cfg=_cfg([{"id": "t1", "name": "EP01", "mp4": "", "style": "",
                   "status": "空闲", "output": ""}]),
        open_window_cb=None, persist_cb=lambda: None)
    seen = []
    panel.taskSelected.connect(seen.append)
    panel.table.setCurrentCell(0, 0)
    assert len(seen) == 1
    v = seen[0]
    assert isinstance(v, _SoundtrackTaskView)
    assert v.id == "t1" and v.name == "EP01"


def test_new_appends_and_selects_new_row():
    _app()
    cfg = _cfg([])
    persisted = []
    panel = SoundtrackPanel(state=None, cfg=cfg, open_window_cb=None,
                            persist_cb=lambda: persisted.append(1))
    seen = []
    panel.taskSelected.connect(seen.append)
    panel._on_new()
    assert len(cfg.soundtrack_tasks) == 1
    assert persisted                       # 落盘被调用
    assert seen and seen[-1].id == cfg.soundtrack_tasks[0]["id"]   # 新行被选中


def test_rename_via_name_column_emits_renamed():
    _app()
    cfg = _cfg([{"id": "t1", "name": "旧名", "mp4": "", "style": "",
                 "status": "空闲", "output": ""}])
    persisted, renamed = [], []
    panel = SoundtrackPanel(state=None, cfg=cfg, open_window_cb=None,
                            persist_cb=lambda: persisted.append(1))
    panel.taskRenamed.connect(lambda tid, name: renamed.append((tid, name)))
    panel.table.item(0, 0).setText("新名字")        # 触发 itemChanged
    assert cfg.soundtrack_tasks[0]["name"] == "新名字"
    assert persisted
    assert renamed == [("t1", "新名字")]


def test_del_emits_task_deleted(monkeypatch):
    _app()
    import drama_shot_master.ui.panels.soundtrack_panel as m
    cfg = _cfg([{"id": "t1", "name": "n", "mp4": "", "style": "",
                 "status": "空闲", "output": ""}])
    panel = SoundtrackPanel(state=None, cfg=cfg, open_window_cb=None,
                            persist_cb=lambda: None)
    deleted = []
    panel.taskDeleted.connect(deleted.append)
    panel.table.setCurrentCell(0, 0)
    monkeypatch.setattr(m.QMessageBox, "question",
                        staticmethod(lambda *a, **k: m.QMessageBox.Yes))
    panel._on_del()
    assert cfg.soundtrack_tasks == []
    assert deleted == ["t1"]
