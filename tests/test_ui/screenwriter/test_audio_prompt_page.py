import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.screenwriter.audio_prompt_page import AudioPromptPage


def _app():
    return QApplication.instance() or QApplication([])


class _Stub:
    pass


def _min_sb():
    return {
        "title": "t", "globalStyle": "ink",
        "characters": [{"name": "周翠英"}, {"name": "李书生"}],
        "shots": [{"shotId": "S01", "duration": 3.0}, {"shotId": "S02", "duration": 4.0}],
    }


def test_constructs():
    _app()
    p = AudioPromptPage(_Stub())
    assert hasattr(p, "_gen_btn")
    assert hasattr(p, "_voice_table")
    assert hasattr(p, "_cue_table")


def test_set_project_none_disables_gen():
    _app()
    p = AudioPromptPage(_Stub())
    p.set_project(None)
    assert p._gen_btn.isEnabled() is False


def test_set_project_with_storyboard_enables_gen(tmp_path):
    _app()
    (tmp_path / "分镜_E1.json").write_text(
        json.dumps(_min_sb()), encoding="utf-8")
    p = AudioPromptPage(_Stub())
    p.set_project(tmp_path)
    assert p._gen_btn.isEnabled() is True


def test_loads_existing_voices(tmp_path):
    _app()
    (tmp_path / "分镜_E1.json").write_text(
        json.dumps(_min_sb()), encoding="utf-8")
    out = tmp_path / "audio_prompts" / "E1"
    out.mkdir(parents=True)
    voices = [{"name": "周翠英", "gender": "女", "age_range": "25岁",
               "tone_description": "柔和", "emotion_range": ["平静"],
               "tts_style_prompt": "gentle"}]
    (out / "voices.json").write_text(json.dumps(voices), encoding="utf-8")
    p = AudioPromptPage(_Stub())
    p.set_project(tmp_path)
    assert p._voice_table.rowCount() == 1


def test_complete_signal_emitted():
    _app()
    p = AudioPromptPage(_Stub())
    received = []
    p.statusMessage.connect(lambda s: received.append(s))
    p._on_complete_clicked()
    assert len(received) == 1


# ── Fix-G: 解包 / 修键 / 复制 toast ──────────────────────────────────

def _wrapped_voices():
    return {"voices": [
        {"name": "女主", "gender": "女", "age_range": "20-25岁",
         "tone_description": "清亮活泼", "emotion_range": ["期待", "惊喜"],
         "tts_style_prompt": "bright, lively"}]}


def _wrapped_cues():
    return {"cues": [
        {"shot_id": "S01_01", "speaker": "女主", "dialogue": "终于到了！",
         "sfx": "胶带声", "bgm_emotion": "喜悦·轻快"},
        {"shot_id": "S01_02", "speaker": "-", "dialogue": "-",
         "sfx": "快递袋声", "bgm_emotion": "神秘·空灵"}]}


def _setup(tmp_path):
    (tmp_path / "分镜_E1.json").write_text(json.dumps(_min_sb()), encoding="utf-8")
    adir = tmp_path / "audio_prompts" / "E1"; adir.mkdir(parents=True)
    (adir / "voices.json").write_text(
        json.dumps(_wrapped_voices(), ensure_ascii=False), encoding="utf-8")
    (adir / "sfx_cues.json").write_text(
        json.dumps(_wrapped_cues(), ensure_ascii=False), encoding="utf-8")


def test_wrapped_voices_populate(tmp_path):
    """voices.json 是 {"voices":[...]} 包裹结构也应正确填表。"""
    _app()
    _setup(tmp_path)
    p = AudioPromptPage(_Stub())
    p.set_project(tmp_path)
    assert p._voice_table.rowCount() == 1
    assert p._voice_table.item(0, p._VCOL_NAME).text() == "女主"


def test_wrapped_cues_populate_real_keys(tmp_path):
    """sfx_cues.json 包裹结构 + shot_id/bgm_emotion 键应正确显示。"""
    _app()
    _setup(tmp_path)
    p = AudioPromptPage(_Stub())
    p.set_project(tmp_path)
    assert p._cue_table.rowCount() == 2
    assert p._cue_table.item(0, p._CCOL_ID).text() == "S01_01"
    assert p._cue_table.item(0, p._CCOL_BGM).text() == "喜悦·轻快"


def test_cue_copy_button_toasts(tmp_path):
    """cue 行有「复制」按钮，复制台词并发 toast（与视频页统一）。"""
    _app()
    _setup(tmp_path)
    p = AudioPromptPage(_Stub())
    p.set_project(tmp_path)
    msgs = []
    p.statusMessage.connect(lambda s: msgs.append(s))
    btn = p._cue_table.cellWidget(0, p._CCOL_COPY)
    assert btn is not None
    btn.click()
    from PySide6.QtWidgets import QApplication as _QA
    assert "终于到了" in _QA.clipboard().text()
    assert msgs and "复制" in msgs[0]
