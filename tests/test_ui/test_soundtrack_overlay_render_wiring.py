"""SoundtrackEditor overlay 渲染接线（子项目 #3c Task 5）。

mock 重组件 / 用 tmp work_dir：
- _refresh_overlay_view 把 segments 推给 track_view + overlay_header；
- overlay 片段点击 handler → _selection 被 clear 且 _current_inspector 是 OverlayInspector；
- lane mute('bgm',0,True) → 该 lane 全段 enabled=False + save_overlay 落盘 + mix_engine.set_segments 被调；
- overlay 空 → _refresh_overlay_view 不抛。
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor
from drama_shot_master.ui.widgets.daw.inspector.overlay_inspector import OverlayInspector


def _app():
    return QApplication.instance() or QApplication([])


def _cfg(tmp_path):
    from drama_shot_master.config import Config
    c = Config(); c.settings_path = tmp_path / "s.json"
    return c


def _ed(tmp_path):
    mp4 = tmp_path / "raw.mp4"; mp4.write_bytes(b"x")
    return SoundtrackEditor({"id": "t1", "name": "t", "mp4": str(mp4),
                             "style": "x", "output_dir": str(tmp_path)},
                            _cfg(tmp_path), tmp_path)


def test_overlay_header_present(tmp_path):
    _app()
    ed = _ed(tmp_path)
    from drama_shot_master.ui.widgets.daw.overlay_header import OverlayHeaderSection
    assert isinstance(ed._overlay_header, OverlayHeaderSection)
    assert ed._overlay_collapsed is False
    assert ed._overlay_sel_id is None


def test_refresh_overlay_view_pushes(tmp_path):
    _app()
    from sound_track_agent.overlay_session import OverlaySession
    ed = _ed(tmp_path)
    sess = OverlaySession(); sess.add("bgm", 0.0, 5.0, "p", seg_id="x1")
    ed._overlay_session = sess
    tv_calls = []; hd_calls = []
    ed._track_view.set_overlay = lambda segs, **kw: tv_calls.append((segs, kw))
    ed._overlay_header.set_overlay = lambda segs, **kw: hd_calls.append((segs, kw))
    ed._refresh_overlay_view()
    assert tv_calls and tv_calls[0][0] == sess.segments
    assert tv_calls[0][1].get("collapsed") is False
    assert hd_calls and hd_calls[0][0] == sess.segments


def test_refresh_track_view_triggers_overlay(tmp_path):
    _app()
    ed = _ed(tmp_path)
    calls = []
    ed._refresh_overlay_view = lambda: calls.append(1)
    ed._refresh_track_view()
    assert calls


def test_overlay_segment_clicked_switches_inspector(tmp_path):
    _app()
    from sound_track_agent.overlay_session import OverlaySession
    ed = _ed(tmp_path)
    sess = OverlaySession(); sess.add("bgm", 0.0, 5.0, "紧张", seg_id="x1")
    ed._overlay_session = sess
    cleared = []
    ed._selection.clear = lambda: cleared.append(1)
    ed._on_overlay_segment_clicked("x1", None)
    assert cleared
    assert ed._overlay_sel_id == "x1"
    assert isinstance(ed._current_inspector, OverlayInspector)


def test_overlay_segment_clicked_missing_seg_empty(tmp_path):
    _app()
    from sound_track_agent.overlay_session import OverlaySession
    from drama_shot_master.ui.widgets.daw.inspector import EmptyInspector
    ed = _ed(tmp_path)
    ed._overlay_session = OverlaySession()
    ed._on_overlay_segment_clicked("nope", None)
    assert isinstance(ed._current_inspector, EmptyInspector)


def test_collapse_toggle(tmp_path):
    _app()
    ed = _ed(tmp_path)
    refreshed = []
    ed._refresh_overlay_view = lambda: refreshed.append(1)
    assert ed._overlay_collapsed is False
    ed._on_overlay_collapse_toggled()
    assert ed._overlay_collapsed is True
    assert refreshed
    ed._on_overlay_collapse_toggled()
    assert ed._overlay_collapsed is False


def test_lane_mute_persists_and_notifies(tmp_path):
    _app()
    from sound_track_agent.overlay_session import OverlaySession, load_overlay
    ed = _ed(tmp_path)
    sess = OverlaySession()
    sess.add("bgm", 0.0, 5.0, "a", seg_id="b0")
    sess.add("bgm", 6.0, 10.0, "b", seg_id="b1")   # 同 lane 0
    sess.add("sfx", 0.0, 2.0, "c", seg_id="s0")
    ed._overlay_session = sess
    set_seg_calls = []
    ed._mix_engine.set_segments = lambda segs: set_seg_calls.append(segs)
    ed._on_overlay_lane_mute("bgm", 0, True)
    # 该 lane 全段 enabled=False
    for s in sess.segments_in_lane("bgm", 0):
        assert s.enabled is False
    # 其它 lane 不动
    assert sess.get("s0").enabled is True
    # 落盘断言
    reloaded = load_overlay(ed._work_dir())
    assert reloaded.get("b0").enabled is False
    assert reloaded.get("b1").enabled is False
    # mix_engine 被刷新
    assert set_seg_calls and set_seg_calls[-1] == sess.segments


def test_lane_volume_persists_and_notifies(tmp_path):
    _app()
    from sound_track_agent.overlay_session import OverlaySession, load_overlay
    ed = _ed(tmp_path)
    sess = OverlaySession()
    sess.add("bgm", 0.0, 5.0, "a", seg_id="b0")
    sess.add("bgm", 6.0, 10.0, "b", seg_id="b1")
    ed._overlay_session = sess
    set_seg_calls = []
    ed._mix_engine.set_segments = lambda segs: set_seg_calls.append(segs)
    ed._on_overlay_lane_volume("bgm", 0, 0.5)
    for s in sess.segments_in_lane("bgm", 0):
        assert s.volume == 0.5
    reloaded = load_overlay(ed._work_dir())
    assert reloaded.get("b0").volume == 0.5
    assert set_seg_calls


def test_refresh_overlay_view_empty_no_raise(tmp_path):
    _app()
    from sound_track_agent.overlay_session import OverlaySession
    ed = _ed(tmp_path)
    ed._overlay_session = OverlaySession()
    ed._refresh_overlay_view()   # 不抛即可


def test_fixed_selection_clears_overlay_sel(tmp_path):
    _app()
    from drama_shot_master.ui.widgets.daw.selection import _CueRef
    ed = _ed(tmp_path)
    ed._overlay_sel_id = "x1"
    # 选中一个固定轨 cue（非 overlay）
    ed._selection.set([_CueRef("video", 0)])
    ed._refresh_inspector()
    assert ed._overlay_sel_id is None
