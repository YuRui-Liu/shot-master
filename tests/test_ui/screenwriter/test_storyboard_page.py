import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter.storyboard_page import StoryboardPage


def _app():
    return QApplication.instance() or QApplication([])


class _StubClient:
    pass


def _sb_fixture():
    return {
        "title": "测试分镜",
        "aspectRatio": "9:16",
        "fps": 24,
        "totalDuration": 12,
        "globalStyle": "古风水墨",
        "characters": [{"name": "狐妖", "appearance": "白衣红眼狐尾披肩长发"}],
        "shots": [
            {"shotId": "S01", "description": "雨夜画面", "duration": 6,
             "composition": "中景",
             "stylePrompt": "古风水墨，雨夜松林，整体调性沉静"},
            {"shotId": "S02", "description": "书生撑伞", "duration": 6,
             "composition": "近景",
             "stylePrompt": "古风水墨，雨夜书生撑伞踱步"},
        ],
    }


def test_set_project_none_disables():
    _app()
    p = StoryboardPage(_StubClient())
    p.set_project(None)
    assert p._gen_btn.isEnabled() is False


def test_load_existing_storyboard_json(tmp_path):
    _app()
    (tmp_path / "分镜.json").write_text(
        json.dumps(_sb_fixture(), ensure_ascii=False), encoding="utf-8")
    p = StoryboardPage(_StubClient())
    p.set_project(tmp_path)
    assert p._state == "done"
    assert p._shots_model.rowCount() == 2
    assert p._title_edit.text() == "测试分镜"
    assert p._global_style_edit.toPlainText() == "古风水墨"
    assert len(p._character_rows) == 1


def test_table_edit_marks_dirty(tmp_path):
    _app()
    (tmp_path / "分镜.json").write_text(
        json.dumps(_sb_fixture(), ensure_ascii=False), encoding="utf-8")
    p = StoryboardPage(_StubClient())
    p.set_project(tmp_path)
    assert p._save_btn.isEnabled() is False
    p._shots_model.setData(p._shots_model.index(0, 3),
                            "改后画面",
                            __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.EditRole)
    assert p._save_btn.isEnabled() is True


def test_save_writes_valid_json(tmp_path):
    _app()
    (tmp_path / "分镜.json").write_text(
        json.dumps(_sb_fixture(), ensure_ascii=False), encoding="utf-8")
    p = StoryboardPage(_StubClient())
    p.set_project(tmp_path)
    p._title_edit.setText("新标题")
    p._on_save_clicked()
    on_disk = json.loads((tmp_path / "分镜.json").read_text(encoding="utf-8"))
    assert on_disk["title"] == "新标题"
    assert p._save_btn.isEnabled() is False


def test_warnings_rendered_when_done_event_has_them(tmp_path):
    _app()
    p = StoryboardPage(_StubClient())
    p.set_project(tmp_path)
    # 模拟 done 事件携带 warnings
    p._on_sse_event("done", {
        "saved": str(tmp_path / "分镜.json"),
        "result": _sb_fixture(),
        "warnings": [
            {"path": "shots[1].stylePrompt", "issue": "过短",
             "severity": "warning"},
        ],
    }, str(tmp_path))
    # isVisible() 需要完整父链可见；headless 下检查 not isHidden() 等价
    assert not p._warnings_banner.isHidden()


def test_upstream_check_blocks_generate(tmp_path, monkeypatch):
    _app()
    p = StoryboardPage(_StubClient())
    p.set_project(tmp_path)   # 没有 剧本.md
    import drama_shot_master.ui.widgets.screenwriter.storyboard_page as m
    called = []
    monkeypatch.setattr(m.QMessageBox, "warning",
                         staticmethod(lambda *a, **k: called.append(True)))
    p._on_generate_clicked()
    assert called


def test_duration_range_spins_default_4_10():
    """默认时长改为范围控件，默认 4–10s。"""
    _app()
    p = StoryboardPage(_StubClient())
    assert p._dur_min_spin.value() == 4.0
    assert p._dur_max_spin.value() == 10.0


def test_generate_body_includes_duration_range(tmp_path):
    """生成请求体应带 shot_duration_min / shot_duration_max。"""
    _app()
    (tmp_path / "剧本_E1.md").write_text("# 测试剧本", encoding="utf-8")
    p = StoryboardPage(_StubClient())
    p.set_project(tmp_path)
    captured = {}
    p._start_stream = lambda path, body, params=None: captured.update(body)
    p._on_generate_clicked()
    opts = captured["options"]
    assert opts["shot_duration_min"] == 4.0
    assert opts["shot_duration_max"] == 10.0


def test_advance_does_not_auto_generate(tmp_path):
    """推进到分镜（start_generation_if_idle）不应自动跑生成——
    用户需先设时长范围，再手动点「生成分镜」。"""
    _app()
    (tmp_path / "剧本_E1.md").write_text("# 测试剧本", encoding="utf-8")
    p = StoryboardPage(_StubClient())
    p.set_project(tmp_path)
    called = []
    p._on_generate_clicked = lambda *a, **k: called.append(True)
    p.start_generation_if_idle()
    assert called == [], "推进不应触发自动生成"


def test_upstream_missing_shows_banner_and_disables_gen(tmp_path):
    _app()
    p = StoryboardPage(_StubClient())
    p.set_project(tmp_path)   # 无 剧本.md
    assert not p._upstream_banner.isHidden()
    assert p._gen_btn.isEnabled() is False


def test_upstream_present_hides_banner(tmp_path):
    _app()
    (tmp_path / "剧本.md").write_text("# 测试", encoding="utf-8")
    p = StoryboardPage(_StubClient())
    p.set_project(tmp_path)
    assert p._upstream_banner.isHidden()


def test_sse_event_for_inactive_project_does_not_touch_table(tmp_path):
    _app()
    p = StoryboardPage(_StubClient())
    pA = tmp_path / "A"; pA.mkdir()
    pB = tmp_path / "B"; pB.mkdir()
    p.set_project(pA)
    rows_before = p._shots_model.rowCount()
    p._on_sse_event("done", {
        "saved": str(pB / "分镜.json"),
        "result": {
            "title": "B 标题", "globalStyle": "x",
            "characters": [], "shots": [{"shotId": "S01", "duration": 1,
                                          "composition": "中", "description": "d",
                                          "stylePrompt": "p"}],
        },
        "warnings": [],
    }, str(pB))
    # 当前显示 A，表格不应变
    assert p._shots_model.rowCount() == rows_before


import json as _json


def test_episode_selector_renders(tmp_path):
    _app()
    (tmp_path / "剧本.json").write_text(_json.dumps({
        "episode_count": 2,
        "episodes": [{"id": "E1", "title": "t", "summary": "s"},
                      {"id": "E2", "title": "t", "summary": "s"}],
    }), encoding="utf-8")
    p = StoryboardPage(_StubClient())
    p.set_project(tmp_path)
    assert p._episode_selector.combo.count() == 2


def test_switch_episode_loads_correct_sb(tmp_path):
    _app()
    (tmp_path / "剧本.json").write_text(_json.dumps({
        "episode_count": 2,
        "episodes": [{"id": "E1", "title": "t", "summary": "s"},
                      {"id": "E2", "title": "t", "summary": "s"}],
    }), encoding="utf-8")
    (tmp_path / "剧本_E1.md").write_text("# E1", encoding="utf-8")
    (tmp_path / "剧本_E2.md").write_text("# E2", encoding="utf-8")
    (tmp_path / "分镜_E2.json").write_text(_json.dumps({
        "title": "E2sb", "aspectRatio": "9:16", "fps": 24,
        "totalDuration": 12, "globalStyle": "x", "characters": [],
        "shots": [
            {"shotId": "S01", "duration": 6, "composition": "中景",
             "description": "d", "stylePrompt": "p"},
            {"shotId": "S02", "duration": 6, "composition": "中景",
             "description": "d2", "stylePrompt": "p2"},
        ],
    }), encoding="utf-8")
    p = StoryboardPage(_StubClient())
    p.set_project(tmp_path)
    p._episode_selector.select_episode("E2")
    p._on_episode_changed("E2")
    assert p._shots_model.rowCount() == 2
    assert p._upstream_banner.isHidden()


def test_switch_episode_upstream_missing_shows_banner(tmp_path):
    _app()
    (tmp_path / "剧本.json").write_text(_json.dumps({
        "episode_count": 2,
        "episodes": [{"id": "E1", "title": "t", "summary": "s"},
                      {"id": "E2", "title": "t", "summary": "s"}],
    }), encoding="utf-8")
    (tmp_path / "剧本_E1.md").write_text("# E1", encoding="utf-8")
    # E2 上游缺失
    p = StoryboardPage(_StubClient())
    p.set_project(tmp_path)
    p._episode_selector.select_episode("E2")
    p._on_episode_changed("E2")
    assert not p._upstream_banner.isHidden()
    assert p._gen_btn.isEnabled() is False


def test_generate_body_includes_episode_id(tmp_path):
    _app()
    (tmp_path / "剧本.json").write_text(_json.dumps({
        "episode_count": 1,
        "episodes": [{"id": "E1", "title": "t", "summary": "s"}],
    }), encoding="utf-8")
    (tmp_path / "剧本_E1.md").write_text("# E1", encoding="utf-8")
    p = StoryboardPage(_StubClient())
    p.set_project(tmp_path)
    captured = {}
    orig_start = p._start_stream
    def _intercept(path, body, params=None):
        captured.update(body)
    p._start_stream = _intercept
    try:
        p._on_generate_clicked()
    except Exception:
        pass
    assert captured.get("episode_id") == "E1"
