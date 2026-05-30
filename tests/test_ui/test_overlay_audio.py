"""OverlayMixer：叠加音轨状态机 + 漂移纠偏阈值。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.overlay_audio import OverlayMixer


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_should_resync_threshold():
    assert OverlayMixer._should_resync(0.0, 0.3) is True     # 漂移 0.3s > 0.2
    assert OverlayMixer._should_resync(1.0, 1.1) is False    # 漂移 0.1s < 0.2


def test_set_track_and_enabled(app, tmp_path):
    wav = tmp_path / "bgm.wav"; wav.write_bytes(b"x")
    m = OverlayMixer()
    m.set_track("bgm", str(wav))
    assert m.track_path("bgm") == str(wav)
    assert m.is_enabled("bgm") is False          # 默认不启用
    m.set_enabled("bgm", True)
    assert m.is_enabled("bgm") is True


def test_set_track_none_clears(app):
    m = OverlayMixer()
    m.set_track("sfx", None)
    assert m.track_path("sfx") is None


def test_volume_clamped(app, tmp_path):
    wav = tmp_path / "b.wav"; wav.write_bytes(b"x")
    m = OverlayMixer()
    m.set_track("bgm", str(wav))
    m.set_volume("bgm", 2.0)
    assert m.volume("bgm") == 1.5                # clamp 上限 1.5
    m.set_volume("bgm", -1.0)
    assert m.volume("bgm") == 0.0


def test_play_pause_does_not_crash_without_tracks(app):
    m = OverlayMixer()
    m.play(); m.pause(); m.stop(); m.seek(1.0); m.sync(1.0)   # 无轨不崩
