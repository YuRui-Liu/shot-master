"""SoundtrackPanel.open_work_dir：含 session.json 的目录 → 反推任务字段。"""
import os, json
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.panels.soundtrack_panel import SoundtrackPanel


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _Cfg:
    def __init__(self):
        self.soundtrack_tasks = []
        self.soundtrack_status_colors = {}


def _panel(app):
    return SoundtrackPanel(state=None, cfg=_Cfg(),
                           open_window_cb=None, persist_cb=lambda: None)


def _make_workdir(tmp_path):
    proj = tmp_path / "02_女剑客归山"
    wd = proj / "17797915850335bf1e"
    wd.mkdir(parents=True)
    (wd / "session.json").write_text(json.dumps({
        "source_mp4": str(proj / "vedio" / "x.mp4"),
        "global_style": "末日",
        "output": str(wd / "scored.mp4"),
    }), encoding="utf-8")
    return wd


def test_open_valid_workdir_appends_task(app, tmp_path):
    p = _panel(app)
    wd = _make_workdir(tmp_path)
    ok = p.open_work_dir(str(wd))
    assert ok is True
    tasks = p._tasks()
    assert len(tasks) == 1
    t = tasks[0]
    assert t["id"] == "17797915850335bf1e"
    assert t["output_dir"] == str(wd.parent)
    assert t["name"] == "02_女剑客归山"
    assert t["mp4"] == str(wd.parent / "vedio" / "x.mp4")
    assert t["style"] == "末日"


def test_open_invalid_dir_returns_false(app, tmp_path):
    p = _panel(app)
    empty = tmp_path / "empty"; empty.mkdir()
    assert p.open_work_dir(str(empty)) is False
    assert p._tasks() == []


def test_open_duplicate_id_no_double_add(app, tmp_path):
    p = _panel(app)
    wd = _make_workdir(tmp_path)
    p.open_work_dir(str(wd))
    p.open_work_dir(str(wd))
    assert len(p._tasks()) == 1
