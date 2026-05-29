"""ScreenwriterTaskManager 测试。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QInputDialog, QFileDialog, QMessageBox

from drama_shot_master.ui.widgets.screenwriter.task_manager import ScreenwriterTaskManager


def _app():
    return QApplication.instance() or QApplication([])


class _StubCfg:
    """模拟 Config：只持 screenwriter_projects + project_root + update_settings。"""
    def __init__(self, projects=None, root=""):
        self.screenwriter_projects = list(projects or [])
        self.screenwriter_project_root = root
        self._saved = {}

    def update_settings(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
        self._saved.update(kw)


def test_refresh_empty_list_shows_no_rows():
    _app()
    tm = ScreenwriterTaskManager(_StubCfg())
    assert tm._table.rowCount() == 0


def test_refresh_renders_status_dots_from_files(tmp_path):
    _app()
    pA = tmp_path / "A"; pA.mkdir()
    (pA / "创意.json").write_text("{}", encoding="utf-8")
    (pA / "剧本.md").write_text("# X", encoding="utf-8")
    cfg = _StubCfg(projects=[str(pA)])
    tm = ScreenwriterTaskManager(cfg)
    assert tm._table.rowCount() == 1
    # 状态点列含 ✓✓○○
    dots = tm._table.item(0, 1).text() if tm._table.item(0, 1) else \
           tm._table.cellWidget(0, 1).text()
    assert "✓" in dots
    assert "○" in dots


def test_refresh_prunes_missing_dirs(tmp_path):
    _app()
    cfg = _StubCfg(projects=[str(tmp_path / "nonexistent")])
    tm = ScreenwriterTaskManager(cfg)
    # 列表里不应有该路径
    assert cfg.screenwriter_projects == []


def test_new_creates_subdir_under_root(tmp_path, monkeypatch):
    _app()
    cfg = _StubCfg(root=str(tmp_path))
    tm = ScreenwriterTaskManager(cfg)
    monkeypatch.setattr(QInputDialog, "getText",
                          staticmethod(lambda *a, **k: ("项目1", True)))
    tm._on_new_clicked()
    assert (tmp_path / "项目1").is_dir()
    assert str(tmp_path / "项目1") in cfg.screenwriter_projects


def test_new_same_name_warns(tmp_path, monkeypatch):
    _app()
    (tmp_path / "A").mkdir()
    cfg = _StubCfg(projects=[str(tmp_path / "A")], root=str(tmp_path))
    tm = ScreenwriterTaskManager(cfg)
    monkeypatch.setattr(QInputDialog, "getText",
                          staticmethod(lambda *a, **k: ("A", True)))
    warned = []
    monkeypatch.setattr(QMessageBox, "warning",
                          staticmethod(lambda *a, **k: warned.append(True)))
    tm._on_new_clicked()
    assert warned


def test_open_adds_external_dir(tmp_path, monkeypatch):
    _app()
    pA = tmp_path / "X"; pA.mkdir()
    cfg = _StubCfg()
    tm = ScreenwriterTaskManager(cfg)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                          staticmethod(lambda *a, **k: str(pA)))
    tm._on_open_clicked()
    assert str(pA) in cfg.screenwriter_projects


def test_open_duplicate_warns(tmp_path, monkeypatch):
    _app()
    pA = tmp_path / "X"; pA.mkdir()
    cfg = _StubCfg(projects=[str(pA)])
    tm = ScreenwriterTaskManager(cfg)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                          staticmethod(lambda *a, **k: str(pA)))
    info = []
    monkeypatch.setattr(QMessageBox, "information",
                          staticmethod(lambda *a, **k: info.append(True)))
    tm._on_open_clicked()
    assert info


def test_delete_list_only_keeps_dir(tmp_path, monkeypatch):
    _app()
    pA = tmp_path / "X"; pA.mkdir()
    cfg = _StubCfg(projects=[str(pA)])
    tm = ScreenwriterTaskManager(cfg)
    tm._table.selectRow(0)
    # mock QMessageBox：点「仅从列表移除」
    class _Box:
        def __init__(self, *a, **k): pass
        def setWindowTitle(self, _): pass
        def setText(self, _): pass
        def addButton(self, label, role=None): return label
        def exec(self): pass
        def clickedButton(self): return "仅从列表移除"
    monkeypatch.setattr("drama_shot_master.ui.widgets.screenwriter.task_manager.QMessageBox",
                         _Box)
    tm._on_delete_clicked()
    assert str(pA) not in cfg.screenwriter_projects
    assert pA.is_dir()  # 目录保留


def test_delete_purge_removes_dir(tmp_path, monkeypatch):
    _app()
    pA = tmp_path / "X"; pA.mkdir()
    (pA / "file.txt").write_text("x", encoding="utf-8")
    cfg = _StubCfg(projects=[str(pA)])
    tm = ScreenwriterTaskManager(cfg)
    tm.set_active_worker_query(lambda p: False)
    tm._table.selectRow(0)
    class _Box:
        def __init__(self, *a, **k): pass
        def setWindowTitle(self, _): pass
        def setText(self, _): pass
        def addButton(self, label, role=None):
            self._label = label
            return label
        def exec(self): pass
        def clickedButton(self): return "连同目录删除"
    monkeypatch.setattr("drama_shot_master.ui.widgets.screenwriter.task_manager.QMessageBox",
                         _Box)
    tm._on_delete_clicked()
    assert str(pA) not in cfg.screenwriter_projects
    assert not pA.is_dir()


def test_delete_blocked_when_worker_active(tmp_path, monkeypatch):
    _app()
    pA = tmp_path / "X"; pA.mkdir()
    cfg = _StubCfg(projects=[str(pA)])
    tm = ScreenwriterTaskManager(cfg)
    tm.set_active_worker_query(lambda p: True)
    tm._table.selectRow(0)
    class _Box:
        def __init__(self, *a, **k): pass
        def setWindowTitle(self, _): pass
        def setText(self, _): pass
        def addButton(self, label, role=None): return label
        def exec(self): pass
        def clickedButton(self): return "连同目录删除"
    monkeypatch.setattr("drama_shot_master.ui.widgets.screenwriter.task_manager.QMessageBox",
                         _Box)
    warned = []
    # 拒绝时的 warning 属于 QMessageBox.warning 静态调用——也 mock
    _Box.warning = staticmethod(lambda *a, **k: warned.append(True))
    tm._on_delete_clicked()
    assert pA.is_dir()
    assert str(pA) in cfg.screenwriter_projects   # 没被删
    assert warned


def test_task_selected_emits_path(tmp_path):
    _app()
    pA = tmp_path / "X"; pA.mkdir()
    cfg = _StubCfg(projects=[str(pA)])
    tm = ScreenwriterTaskManager(cfg)
    got = []
    tm.taskSelected.connect(got.append)
    # selectRow triggers itemSelectionChanged -> _on_selection_changed automatically
    tm._table.selectRow(0)
    assert pA in got


def test_refresh_preserves_selection_and_does_not_clear(tmp_path):
    """Bug 修复回归：30s 定时 refresh 不应清除选中、不应误发 taskSelected(None)。"""
    _app()
    pA = tmp_path / "A"; pA.mkdir()
    pB = tmp_path / "B"; pB.mkdir()
    cfg = _StubCfg(projects=[str(pA), str(pB)])
    tm = ScreenwriterTaskManager(cfg)
    tm._table.selectRow(0)
    # 选 A 后清掉初始 selectRow 触发的 taskSelected 事件，只观察 refresh 期间
    events = []
    tm.taskSelected.connect(events.append)
    tm.refresh()
    # 选中仍是 A
    assert tm._selected_project() == pA
    # refresh 不应触发 taskSelected（不论是 None 还是同值）
    assert events == []


def test_refresh_drops_selection_only_if_project_pruned(tmp_path):
    """剪枝后被选中项目若消失，selection 应为空（不要假装还在）。"""
    _app()
    pA = tmp_path / "A"; pA.mkdir()
    cfg = _StubCfg(projects=[str(pA)])
    tm = ScreenwriterTaskManager(cfg)
    tm._table.selectRow(0)
    import shutil
    shutil.rmtree(pA)
    tm.refresh()
    assert tm._selected_project() is None
