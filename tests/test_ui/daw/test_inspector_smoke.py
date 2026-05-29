"""4 Inspector 模板 smoke: 字段齐 + 信号 emit."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from sound_track_agent.session import SegmentScore, ScoringSession, BGMCandidate
from sound_track_agent.sfx.session import SFXSession, SFXShot, SFXCandidate
from drama_shot_master.ui.widgets.daw.selection import _CueRef


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_empty_inspector_construct(app):
    from drama_shot_master.ui.widgets.daw.inspector.empty_inspector \
        import EmptyInspector
    w = EmptyInspector()
    assert w is not None


def test_bgm_inspector_displays_cue_fields(app):
    from drama_shot_master.ui.widgets.daw.inspector.bgm_inspector \
        import BgmInspector
    bgm = ScoringSession(source_mp4="/m.mp4", source_hash="h",
                         global_style="末日", frame_rate=24.0,
                         segments=[SegmentScore(
                             0, 0.0, 5.0, music_prompt="末日废土",
                             candidates=[BGMCandidate(path="/a.mp3", seed=1, prompt="x")],
                             chosen_candidate=0)])
    w = BgmInspector()
    w.set_cue_ref(_CueRef("bgm", 0), bgm)
    assert hasattr(w, "btn_regen")
    assert hasattr(w, "btn_edit_prompt")


def test_bgm_inspector_regenerate_signal(app):
    from drama_shot_master.ui.widgets.daw.inspector.bgm_inspector \
        import BgmInspector
    bgm = ScoringSession(source_mp4="/m.mp4", source_hash="h",
                         global_style="末日", frame_rate=24.0,
                         segments=[SegmentScore(0, 0.0, 5.0)])
    w = BgmInspector()
    w.set_cue_ref(_CueRef("bgm", 0), bgm)
    received = []
    w.regenerateRequested.connect(lambda ref: received.append(ref))
    w.btn_regen.click()
    assert len(received) == 1


def test_sfx_inspector_duration_spin_changes_emit_resize_command(app):
    from drama_shot_master.ui.widgets.daw.inspector.sfx_inspector \
        import SfxInspector
    sfx = SFXSession(source_mp4="/m.mp4", source_hash="h", frame_rate=24.0,
                     shots=[SFXShot(0, 0.0, 3.0, duration=3.0,
                                     prompt_short="门")])
    w = SfxInspector()
    w.set_cue_ref(_CueRef("sfx", 0), sfx)
    cmds = []
    w.commandIssued.connect(lambda c: cmds.append(c))
    w.duration_spin.setValue(5.0)     # 3.0 → 5.0，dt = +2.0
    from drama_shot_master.ui.widgets.daw.commands import ResizeCue
    assert any(isinstance(c, ResizeCue) for c in cmds)


def test_dialogue_inspector_is_readonly(app):
    from drama_shot_master.ui.widgets.daw.inspector.dialogue_inspector \
        import DialogueInspector
    audios = [{
        "audio_path": "/x/voice_charA_01.flac",
        "start_frame": 0, "length_frames": 72,
    }]
    timeline = {"frame_rate": 24.0, "audios": audios}
    w = DialogueInspector()
    w.set_cue_ref(_CueRef("dialogue", 0), timeline)
    from PySide6.QtWidgets import QLineEdit
    edits = w.findChildren(QLineEdit)
    for e in edits:
        assert e.isReadOnly()
