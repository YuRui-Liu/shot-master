import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.screenwriter.video_prompt_page import VideoPromptPage


def _app():
    return QApplication.instance() or QApplication([])


class _Stub:
    pass


def _min_sb():
    return {
        "title": "test", "globalStyle": "ink-wash",
        "characters": [{"name": "A"}],
        "shots": [{"shotId": "S01", "duration": 3.0}],
    }


def test_constructs():
    _app()
    p = VideoPromptPage(_Stub())
    assert hasattr(p, "_gen_btn")
    assert hasattr(p, "_global_prompt_edit")
    assert hasattr(p, "_shots_table")


def test_set_project_none_disables_gen():
    _app()
    p = VideoPromptPage(_Stub())
    p.set_project(None)
    assert p._gen_btn.isEnabled() is False


def test_set_project_no_storyboard_disables_gen(tmp_path):
    _app()
    p = VideoPromptPage(_Stub())
    p.set_project(tmp_path)
    assert p._gen_btn.isEnabled() is False


def test_set_project_with_storyboard_enables_gen(tmp_path):
    _app()
    (tmp_path / "分镜_E1.json").write_text(
        json.dumps(_min_sb()), encoding="utf-8")
    p = VideoPromptPage(_Stub())
    p.set_project(tmp_path)
    assert p._gen_btn.isEnabled() is True


def test_advance_signal_emitted():
    _app()
    p = VideoPromptPage(_Stub())
    received = []
    p.stageAdvanceRequested.connect(lambda i: received.append(i))
    p._on_advance_clicked()
    assert received == [4]           # Stage 5 = index 4


# ── Fix-F: 去头 / 加复制 / 修键 / toast ──────────────────────────────

def _real_shots():
    """实际后端键：shot_id / local_prompt / duration_s。"""
    return [
        {"shot_id": "S01_01", "local_prompt": "Camera: medium.", "duration_s": 5.0},
        {"shot_id": "S01_02", "local_prompt": "Camera: push-in.", "duration_s": 4.0},
    ]


def test_shots_table_reads_real_keys(tmp_path):
    """ID 列读 shot_id、时长列读 duration_s（不再是空）。"""
    _app()
    (tmp_path / "分镜_E1.json").write_text(json.dumps(_min_sb()), encoding="utf-8")
    vdir = tmp_path / "video_prompts" / "E1"; vdir.mkdir(parents=True)
    (vdir / "global.md").write_text("clean prompt", encoding="utf-8")
    (vdir / "shots.json").write_text(json.dumps(_real_shots()), encoding="utf-8")
    p = VideoPromptPage(_Stub())
    p.set_project(tmp_path)
    assert p._shots_table.item(0, p._COL_ID).text() == "S01_01"
    assert p._shots_table.item(0, p._COL_DUR).text() == "5.0"


def test_global_md_header_stripped_on_load(tmp_path):
    """已有 global.md 带 '# global_prompt' 头时，UI 显示应去头。"""
    _app()
    (tmp_path / "分镜_E1.json").write_text(json.dumps(_min_sb()), encoding="utf-8")
    vdir = tmp_path / "video_prompts" / "E1"; vdir.mkdir(parents=True)
    (vdir / "global.md").write_text(
        "# global_prompt\n\nModern style, warm tones.", encoding="utf-8")
    (vdir / "shots.json").write_text("[]", encoding="utf-8")
    p = VideoPromptPage(_Stub())
    p.set_project(tmp_path)
    txt = p._global_prompt_edit.toPlainText()
    assert "# global_prompt" not in txt
    assert txt.strip() == "Modern style, warm tones."


def test_global_copy_button_exists_and_toasts():
    """全局面板有复制按钮，点击发 statusMessage toast。"""
    _app()
    p = VideoPromptPage(_Stub())
    assert hasattr(p, "_global_copy_btn")
    p._global_prompt_edit.setPlainText("hello prompt")
    msgs = []
    p.statusMessage.connect(lambda s: msgs.append(s))
    p._global_copy_btn.click()
    from PySide6.QtWidgets import QApplication as _QA
    assert _QA.clipboard().text() == "hello prompt"
    assert msgs and "复制" in msgs[0]


# ── Fix-J: 模板下拉 + 语言切换 + 持久化 ──────────────────────────────

def test_template_and_language_controls_exist_defaults():
    """工具栏有模板下拉 + 语言下拉，默认 ltx / en。"""
    _app()
    p = VideoPromptPage(_Stub())
    assert hasattr(p, "_template_combo")
    assert hasattr(p, "_lang_combo")
    assert p.current_template_id() == "ltx"
    assert p.current_language() == "en"


def test_generate_body_includes_template_and_language(tmp_path):
    """生成请求体 options 带 template_id + language。"""
    _app()
    (tmp_path / "分镜_E1.json").write_text(json.dumps(_min_sb()), encoding="utf-8")
    p = VideoPromptPage(_Stub())
    p.set_project(tmp_path)
    captured = {}
    p._start_stream = lambda path, body, params=None: captured.update(body)
    p._on_generate_clicked()
    opts = captured["options"]
    assert opts["template_id"] == "ltx"
    assert opts["language"] == "en"


def test_template_choice_persists_per_project(tmp_path):
    """切到简洁/中文 → 存 video_prompts/_config.json → 重载项目恢复。"""
    _app()
    (tmp_path / "分镜_E1.json").write_text(json.dumps(_min_sb()), encoding="utf-8")
    p = VideoPromptPage(_Stub())
    p.set_project(tmp_path)
    p.set_template_id("simple")
    p.set_language("zh")
    assert (tmp_path / "video_prompts" / "_config.json").is_file()
    # 新页面重载同项目
    p2 = VideoPromptPage(_Stub())
    p2.set_project(tmp_path)
    assert p2.current_template_id() == "simple"
    assert p2.current_language() == "zh"


# ── Fix-K: 复制按钮不裁切（Fixed 列宽 + minWidth）──────────────────────

def test_shots_copy_button_not_clipped(tmp_path):
    _app()
    (tmp_path / "分镜_E1.json").write_text(json.dumps(_min_sb()), encoding="utf-8")
    vdir = tmp_path / "video_prompts" / "E1"; vdir.mkdir(parents=True)
    (vdir / "global.md").write_text("x", encoding="utf-8")
    (vdir / "shots.json").write_text(json.dumps(_real_shots()), encoding="utf-8")
    p = VideoPromptPage(_Stub())
    p.set_project(tmp_path)
    btn = p._shots_table.cellWidget(0, p._COL_COPY)
    assert btn is not None and btn.minimumWidth() >= 56
    assert p._shots_table.columnWidth(p._COL_COPY) >= 56


def test_global_copy_shows_visible_toast():
    """复制后出现可见 toast（不依赖 app-shell 死掉的 statusMessage 链）。"""
    _app()
    p = VideoPromptPage(_Stub())
    p.resize(400, 300)
    p._global_prompt_edit.setPlainText("hello")
    p._global_copy_btn.click()
    t = getattr(p, "_toast_widget", None)
    assert t is not None and not t.isHidden()
    assert "复制" in t.text()


# ── 单文件合并：shots.json 对象格式 + 旧两文件回退 ──────────────────

def test_load_new_object_format(tmp_path):
    """shots.json 为对象 {global_prompt, shots} → 全局框 + 表都填充。"""
    _app()
    (tmp_path / "分镜_E1.json").write_text(json.dumps(_min_sb()), encoding="utf-8")
    vdir = tmp_path / "video_prompts" / "E1"; vdir.mkdir(parents=True)
    (vdir / "shots.json").write_text(json.dumps({
        "global_prompt": "GP-NEW",
        "shots": [{"shot_id": "S01_01", "local_prompt": "x", "duration_s": 5.0}],
    }), encoding="utf-8")
    p = VideoPromptPage(_Stub())
    p.set_project(tmp_path)
    assert p._global_prompt_edit.toPlainText().strip() == "GP-NEW"
    assert p._shots_table.item(0, p._COL_ID).text() == "S01_01"
    assert p._shots_table.item(0, p._COL_DUR).text() == "5.0"


def test_load_legacy_two_files_fallback(tmp_path):
    """旧格式：global.md + shots.json 裸数组 → 回退读，全局来自 global.md。"""
    _app()
    (tmp_path / "分镜_E1.json").write_text(json.dumps(_min_sb()), encoding="utf-8")
    vdir = tmp_path / "video_prompts" / "E1"; vdir.mkdir(parents=True)
    (vdir / "global.md").write_text(
        "# global_prompt\n\nGP-OLD", encoding="utf-8")
    (vdir / "shots.json").write_text(json.dumps(
        [{"shot_id": "S01_02", "local_prompt": "y", "duration_s": 4.0}]),
        encoding="utf-8")
    p = VideoPromptPage(_Stub())
    p.set_project(tmp_path)
    assert p._global_prompt_edit.toPlainText().strip() == "GP-OLD"   # 去头
    assert p._shots_table.item(0, p._COL_ID).text() == "S01_02"
