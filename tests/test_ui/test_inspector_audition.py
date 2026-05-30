"""Inspector 候选 ▶ 试听：每候选有播放按钮，点击切 ⏸ 并播放该候选 path。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from sound_track_agent.session import ScoringSession, SegmentScore, BGMCandidate
from sound_track_agent.sfx.session import SFXSession, SFXShot, SFXCandidate
from drama_shot_master.ui.widgets.daw.selection import _CueRef


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_bgm_inspector_has_play_button_per_candidate(app, tmp_path):
    from drama_shot_master.ui.widgets.daw.inspector.bgm_inspector import BgmInspector
    mp3 = tmp_path / "a.mp3"; mp3.write_bytes(b"x")
    bgm = ScoringSession(source_mp4="", source_hash="", global_style="x",
                         frame_rate=24.0,
                         segments=[SegmentScore(0, 0.0, 5.0,
                             candidates=[BGMCandidate(path=str(mp3), seed=1, prompt="p")],
                             chosen_candidate=0)])
    w = BgmInspector()
    w.set_cue_ref(_CueRef("bgm", 0), bgm)
    assert len(w._play_buttons) == 1
    assert w._play_buttons[0].text() == "▶"


def test_bgm_play_button_toggles_and_plays(app, tmp_path):
    from drama_shot_master.ui.widgets.daw.inspector.bgm_inspector import BgmInspector
    mp3 = tmp_path / "a.mp3"; mp3.write_bytes(b"x")
    bgm = ScoringSession(source_mp4="", source_hash="", global_style="x",
                         frame_rate=24.0,
                         segments=[SegmentScore(0, 0.0, 5.0,
                             candidates=[BGMCandidate(path=str(mp3), seed=1, prompt="p")],
                             chosen_candidate=0)])
    w = BgmInspector()
    w.set_cue_ref(_CueRef("bgm", 0), bgm)
    played = []
    w._audition.set_track = lambda name, path: played.append(path)  # 截获
    w._audition.play = lambda: played.append("PLAY")
    w._play_buttons[0].click()
    assert str(mp3) in played and "PLAY" in played
    assert w._play_buttons[0].text() == "⏸"


def test_bgm_missing_file_disables_button(app, tmp_path):
    from drama_shot_master.ui.widgets.daw.inspector.bgm_inspector import BgmInspector
    bgm = ScoringSession(source_mp4="", source_hash="", global_style="x",
                         frame_rate=24.0,
                         segments=[SegmentScore(0, 0.0, 5.0,
                             candidates=[BGMCandidate(path="/no/such.mp3", seed=1, prompt="p")],
                             chosen_candidate=0)])
    w = BgmInspector()
    w.set_cue_ref(_CueRef("bgm", 0), bgm)
    assert w._play_buttons[0].isEnabled() is False


def test_sfx_inspector_has_play_button_per_candidate(app, tmp_path):
    from drama_shot_master.ui.widgets.daw.inspector.sfx_inspector import SfxInspector
    mp3 = tmp_path / "s.mp3"; mp3.write_bytes(b"x")
    sfx = SFXSession(source_mp4="", source_hash="", frame_rate=24.0,
                     shots=[SFXShot(0, 0.0, 3.0, duration=3.0, prompt_short="门",
                            candidates=[SFXCandidate(path=str(mp3), seed=1, prompt="p")],
                            chosen_candidate=0)])
    w = SfxInspector()
    w.set_cue_ref(_CueRef("sfx", 0), sfx)
    assert len(w._play_buttons) == 1
