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
        segments=[SegmentScore(index=0, t_start=0.0, t_end=4.0),
                  SegmentScore(index=1, t_start=4.0, t_end=8.0)],
        accent_points=[AccentPoint(t=2.4, intensity=0.9),
                       AccentPoint(t=6.7, intensity=0.8)])


def test_accent_lists_existing():
    _app()
    w = AccentEditorWidget(_sess())
    assert w.accent_count() == 2
    assert w.listw.count() == 2


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


def test_timeline_total_spans_segments_and_accents():
    _app()
    s = _sess()
    s.accent_points.append(AccentPoint(t=12.0, intensity=1.0))
    w = AccentEditorWidget(s)
    assert w.timeline._total() == 12.0          # 爆点超出段末 → 取爆点
    s2 = ScoringSession(source_mp4="/x", source_hash="h", global_style="s",
                        frame_rate=24.0,
                        segments=[SegmentScore(index=0, t_start=0.0, t_end=8.0)])
    w2 = AccentEditorWidget(s2)
    assert w2.timeline._total() == 8.0          # 无爆点 → 取段末


def test_auto_detect_applies_points_and_emits():
    _app()
    sess = _sess()
    w = AccentEditorWidget(sess)
    seen = []
    w.accentsChanged.connect(lambda: seen.append(1))
    # 直接走应用回调（绕开线程/光流），等价于 worker 完成
    w._apply_detected([AccentPoint(t=1.0, intensity=0.5),
                       AccentPoint(t=5.0, intensity=0.8)])
    assert w.accent_count() == 2 and seen
    assert w.btn_detect.isEnabled()
    assert "2" in w.status_label.text()


def test_auto_detect_missing_video_warns_not_crash(monkeypatch):
    _app()
    import drama_shot_master.ui.widgets.accent_editor_widget as m
    monkeypatch.setattr(m.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: None))
    w = AccentEditorWidget(_sess())     # source_mp4="/x" 不存在 → 不启动 worker
    w._on_auto_detect()
    assert w._worker is None
    assert w.btn_detect.isEnabled()


def test_timeline_selection_syncs_list():
    _app()
    w = AccentEditorWidget(_sess())
    w._on_timeline_select(1)
    assert w.listw.currentRow() == 1
