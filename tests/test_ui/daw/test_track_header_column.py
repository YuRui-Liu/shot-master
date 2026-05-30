"""TrackHeaderColumn：三轨 M/S/音量行 + dialogue 只读 + 信号 + set_state。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.daw.track_mix import TrackMixState
from drama_shot_master.ui.widgets.daw.track_header_column import TrackHeaderColumn


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_construct_has_three_audio_rows(app):
    w = TrackHeaderColumn()
    for t in ("video", "bgm", "sfx"):
        assert t in w._rows
    assert "dialogue" not in w._rows


def test_mute_button_emits(app):
    w = TrackHeaderColumn()
    got = []
    w.muteToggled.connect(lambda t, on: got.append((t, on)))
    w._rows["bgm"]["mute"].click()
    assert got == [("bgm", True)]


def test_solo_button_emits(app):
    w = TrackHeaderColumn()
    got = []
    w.soloToggled.connect(lambda t, on: got.append((t, on)))
    w._rows["sfx"]["solo"].click()
    assert got == [("sfx", True)]


def test_volume_slider_emits(app):
    w = TrackHeaderColumn()
    got = []
    w.volumeChanged.connect(lambda t, v: got.append((t, v)))
    w._rows["video"]["vol"].setValue(50)
    assert got and got[-1][0] == "video"
    assert abs(got[-1][1] - 0.5) < 1e-6


def test_set_state_reflects_mute_solo(app):
    w = TrackHeaderColumn()
    m = TrackMixState(); m.set_muted("bgm", True); m.set_soloed("sfx", True)
    w.set_state(m)
    assert w._rows["bgm"]["mute"].isChecked() is True
    assert w._rows["sfx"]["solo"].isChecked() is True
    assert w._rows["video"]["mute"].isChecked() is False
