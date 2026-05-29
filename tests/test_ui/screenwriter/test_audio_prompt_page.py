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
