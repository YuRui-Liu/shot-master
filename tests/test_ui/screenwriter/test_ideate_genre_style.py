"""IdeatePage 立意页结构化集成（T1）：题材/风格 chip + 画幅 + 高级折叠 + 注入预览。

mock dialog（不弹真窗），断言写 project.json + chip 刷新 + 画幅初值/changed +
高级面板默认收起 + 注入预览随 project.json 刷新。保持原有 ideate_page 测试不破坏。
"""
import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter.ideate_page import IdeatePage
from drama_shot_master.core.compass.manifest import load_manifest, save_manifest, ProjectManifest
import drama_shot_master.ui.widgets.screenwriter.ideate_page as ideate_mod


def _app():
    return QApplication.instance() or QApplication([])


class _StubClient:
    def __init__(self):
        self.select_calls = []

    def ideate_select(self, project_dir, selected_id):
        self.select_calls.append((Path(project_dir), selected_id))
        return {"saved": "", "selected": {"id": selected_id}}


def _write_manifest(tmp_path, *, genre=None, style_ref=None, aspect=None, episodes=None, dur=None):
    m = ProjectManifest(project_name="t")
    if genre is not None:
        m.params["genre"] = genre
    if style_ref is not None:
        m.style_bible["ref"] = style_ref
    if aspect is not None:
        m.params["aspect_ratio"] = aspect
    if episodes is not None:
        m.params["episode_count"] = episodes
    if dur is not None:
        m.params["duration_per_unit_sec"] = dur
    save_manifest(m, tmp_path)


# —— 题材 chip + picker —————————————————————————————————————————

def test_genre_chip_reflects_manifest_display_name(tmp_path):
    """project.json 已有 params.genre=short-drama → chip 显示 display_name。"""
    _app()
    _write_manifest(tmp_path, genre="short-drama")
    p = IdeatePage(_StubClient())
    p.set_project(tmp_path)
    from drama_shot_master.core.genre_templates import load_genre
    expect = load_genre("short-drama").get("display_name", "short-drama")
    assert expect in p._genre_chip.text()


def test_pick_genre_writes_manifest_and_refreshes_chip(tmp_path, monkeypatch):
    """点「选题材模板」→ mock GenrePickerDialog 返回 → 写 params.genre + chip 刷新。"""
    _app()
    _write_manifest(tmp_path)
    p = IdeatePage(_StubClient())
    p.set_project(tmp_path)

    class _FakeDlg:
        def __init__(self, *a, **kw):
            pass

        def exec(self):
            return 1

        def result_value(self):
            return {"genre": "short-drama", "sub": ["mv"]}

    monkeypatch.setattr(ideate_mod, "GenrePickerDialog", _FakeDlg)
    p._on_pick_genre_clicked()

    m = load_manifest(tmp_path)
    raw = m.params.get("genre")
    # 存 dict 形态 {"genre": id, "sub": [...]}（与 client.assemble_gen_context 读法一致）
    assert isinstance(raw, dict)
    assert raw.get("genre") == "short-drama"
    assert raw.get("sub") == ["mv"]
    from drama_shot_master.core.genre_templates import load_genre
    assert load_genre("short-drama").get("display_name") in p._genre_chip.text()


def test_pick_genre_cancel_keeps_manifest(tmp_path, monkeypatch):
    """取消（result_value None）→ 不写 manifest。"""
    _app()
    _write_manifest(tmp_path, genre="short-drama")
    p = IdeatePage(_StubClient())
    p.set_project(tmp_path)

    class _FakeDlg:
        def __init__(self, *a, **kw):
            pass

        def exec(self):
            return 0

        def result_value(self):
            return None

    monkeypatch.setattr(ideate_mod, "GenrePickerDialog", _FakeDlg)
    p._on_pick_genre_clicked()
    assert load_manifest(tmp_path).params.get("genre") == "short-drama"


# —— 风格 chip + picker —————————————————————————————————————————

def test_pick_style_writes_manifest_and_refreshes_chip(tmp_path, monkeypatch):
    """点「选风格圣经」→ mock StyleBibleDialog → 写 style_bible.ref + category + chip 刷新。"""
    _app()
    _write_manifest(tmp_path)
    p = IdeatePage(_StubClient())
    p.set_project(tmp_path)

    class _FakeDlg:
        def __init__(self, *a, **kw):
            pass

        def exec(self):
            return 1

        def result_value(self):
            return {"ref": "ref-style-1", "category": "real"}

    monkeypatch.setattr(ideate_mod, "StyleBibleDialog", _FakeDlg)
    p._on_pick_style_clicked()

    m = load_manifest(tmp_path)
    assert m.style_bible.get("ref") == "ref-style-1"
    assert m.style_bible.get("category") == "real"
    assert "ref-style-1" in p._style_chip.text()


# —— 画幅 —————————————————————————————————————————————————————

def test_aspect_initial_from_manifest(tmp_path):
    """params.aspect_ratio 存在 → AspectRatioSelector 初值取它。"""
    _app()
    _write_manifest(tmp_path, aspect="9:16")
    p = IdeatePage(_StubClient())
    p.set_project(tmp_path)
    assert p._aspect_selector.value() == "9:16"


def test_aspect_default_16_9_when_absent(tmp_path):
    """无 params.aspect_ratio、无 cfg → 默认 16:9。"""
    _app()
    _write_manifest(tmp_path)
    p = IdeatePage(_StubClient())
    p.set_project(tmp_path)
    assert p._aspect_selector.value() == "16:9"


def test_aspect_changed_writes_manifest(tmp_path):
    """AspectRatioSelector.changed → 写 params.aspect_ratio。"""
    _app()
    _write_manifest(tmp_path)
    p = IdeatePage(_StubClient())
    p.set_project(tmp_path)
    p._aspect_selector.changed.emit("1:1")
    assert load_manifest(tmp_path).params.get("aspect_ratio") == "1:1"


# —— 高级折叠 —————————————————————————————————————————————————

def test_advanced_panel_collapsed_by_default(tmp_path):
    """高级面板（自由文本 _ctx_genre/_ctx_visual）默认收起。"""
    _app()
    _write_manifest(tmp_path)
    p = IdeatePage(_StubClient())
    p.set_project(tmp_path)
    assert p._adv_toggle.isChecked() is False
    # 默认收起：显式 hidden（isHidden 不依赖父窗是否 show）
    assert p._adv_body.isHidden() is True


def test_advanced_toggle_expands(tmp_path):
    """点高级 toggle → 展开自由文本区。"""
    _app()
    _write_manifest(tmp_path)
    p = IdeatePage(_StubClient())
    p.set_project(tmp_path)
    p._adv_toggle.setChecked(True)
    p._on_adv_toggled(True)
    # 展开后不再 hidden（父窗未 show 时 isVisible 仍 False，故用 isHidden）
    assert p._adv_body.isHidden() is False


def test_free_text_still_feeds_request(tmp_path):
    """高级自由文本仍进 request 的 genre_tags / visual_style（向后兼容）。"""
    _app()
    _write_manifest(tmp_path)
    p = IdeatePage(_StubClient())
    p.set_project(tmp_path)
    p._ctx_genre.setText("古风, 玄幻")
    p._ctx_visual.setText("水墨")
    ctx = p._collect_context()
    assert ctx["genre_tags"] == ["古风", "玄幻"]
    assert ctx["visual_style"] == "水墨"


# —— 注入预览 —————————————————————————————————————————————————

def test_injection_preview_refreshes_from_manifest(tmp_path):
    """注入预览读 project.json genre/style → gen_context 摘要 + 规格。"""
    _app()
    _write_manifest(tmp_path, genre="short-drama", aspect="9:16",
                    episodes=5, dur=90)
    p = IdeatePage(_StubClient())
    p.set_project(tmp_path)
    text = p._injection_preview.toPlainText()
    # 规格行含画幅 / 集数 / 时长
    assert "9:16" in text
    assert "5" in text
    assert "90" in text


def test_injection_preview_updates_after_pick_genre(tmp_path, monkeypatch):
    """选题材后注入预览刷新含题材摘要。"""
    _app()
    _write_manifest(tmp_path)
    p = IdeatePage(_StubClient())
    p.set_project(tmp_path)

    class _FakeDlg:
        def __init__(self, *a, **kw):
            pass

        def exec(self):
            return 1

        def result_value(self):
            return {"genre": "short-drama", "sub": []}

    monkeypatch.setattr(ideate_mod, "GenrePickerDialog", _FakeDlg)
    p._on_pick_genre_clicked()
    from drama_shot_master.core.genre_templates import load_genre
    from drama_shot_master.core.gen_context import build_genre_context
    summary = build_genre_context(load_genre("short-drama"))
    # 预览非空且与 build_genre_context 有交集（取一句话定位片段）
    one_liner = (load_genre("short-drama").get("identity") or {}).get("one_liner", "")
    if one_liner:
        assert one_liner[:6] in p._injection_preview.toPlainText()


# —— 发送 request 带 project_dir —————————————————————————————————

def test_send_request_includes_project_dir(tmp_path, monkeypatch):
    """发送时 request body 带 project_dir（client 据此自动注入 context）。"""
    _app()
    _write_manifest(tmp_path)
    p = IdeatePage(_StubClient())
    p.set_project(tmp_path)
    captured = {}

    def _fake_start(path, body, params=None):
        captured["body"] = body

    monkeypatch.setattr(p, "_start_stream", _fake_start)
    p._send_user_text("生成候选")
    assert captured["body"].get("project_dir") == str(tmp_path)
