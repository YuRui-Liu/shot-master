"""OverlayInspector smoke: 纯只读字段展示 + 音频状态判定."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from sound_track_agent.overlay_session import OverlaySegment


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _seg(**kw):
    base = dict(id="s1", kind="bgm", lane=0, t_start=5.0, t_end=10.0,
                prompt="紧张配乐", audio_path="x.mp3", volume=0.8, enabled=True)
    base.update(kw)
    return OverlaySegment(**base)


def test_overlay_inspector_displays_fields(app):
    from drama_shot_master.ui.widgets.daw.inspector.overlay_inspector \
        import OverlayInspector
    w = OverlayInspector()
    w.set_segment(_seg())
    assert "BGM" in w.title.text()
    assert "0" in w.title.text()           # lane0
    assert "5" in w.time_label.text()
    assert "紧张配乐" in w.prompt_label.text()
    assert "80%" in w.volume_label.text()
    assert "已生成" in w.audio_label.text()


def test_overlay_inspector_sfx_lane1(app):
    from drama_shot_master.ui.widgets.daw.inspector.overlay_inspector \
        import OverlayInspector
    w = OverlayInspector()
    w.set_segment(_seg(kind="sfx", lane=1))
    assert "SFX" in w.title.text()
    assert "1" in w.title.text()


def test_overlay_inspector_no_audio(app):
    from drama_shot_master.ui.widgets.daw.inspector.overlay_inspector \
        import OverlayInspector
    w = OverlayInspector()
    w.set_segment(_seg(audio_path=""))
    assert "未生成" in w.audio_label.text()


def test_overlay_inspector_prompt_wraps(app):
    from drama_shot_master.ui.widgets.daw.inspector.overlay_inspector \
        import OverlayInspector
    w = OverlayInspector()
    assert w.prompt_label.wordWrap()
