import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.accent_editor_widget import AccentEditorWidget
from sound_track_agent.session import ScoringSession, SegmentScore, AccentPoint


def _app():
    return QApplication.instance() or QApplication([])


def _sess():
    return ScoringSession(
        source_mp4="/x", source_hash="h", global_style="s", frame_rate=24.0,
        segments=[SegmentScore(index=0, t_start=0.0, t_end=8.0)],
        accent_points=[AccentPoint(t=2.4, intensity=0.9),
                       AccentPoint(t=6.7, intensity=0.8)])


def test_accent_lists_existing():
    _app()
    w = AccentEditorWidget(_sess())
    assert w.accent_count() == 2


def test_accent_add_and_delete():
    _app()
    sess = _sess()
    w = AccentEditorWidget(sess)
    seen = []
    w.accentsChanged.connect(lambda: seen.append(1))
    w.add_accent(5.0)
    assert w.accent_count() == 3
    assert any(abs(a.t - 5.0) < 1e-6 and a.confirmed for a in sess.accent_points)
    w.delete_accent(0)
    assert w.accent_count() == 2
    assert len(seen) >= 2


def test_accent_nudge():
    _app()
    sess = _sess()
    w = AccentEditorWidget(sess)
    w.nudge_accent(0, 0.1)
    ts = sorted(a.t for a in sess.accent_points)
    assert abs(ts[0] - 2.5) < 1e-6
