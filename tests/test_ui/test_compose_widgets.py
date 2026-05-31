import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


def test_clip_strip_emits_signals():
    _app()
    from drama_shot_master.core.composition_model import ReelClip, CompositionModel
    from drama_shot_master.ui.widgets.compose.clip_strip import ClipStrip
    m = CompositionModel(clips=[ReelClip.new(path="/0.mp4", duration=8),
                                ReelClip.new(path="/1.mp4", duration=6)])
    strip = ClipStrip()
    strip.set_model(m)
    got = []
    strip.clipSelected.connect(lambda cid: got.append(("clip", cid)))
    strip.connectorSelected.connect(lambda i: got.append(("conn", i)))
    strip.keepToggled.connect(lambda cid, k: got.append(("keep", cid, k)))
    strip.select_clip(m.clips[0].clip_id)
    strip.select_connector(0)
    strip.toggle_keep(m.clips[1].clip_id)
    assert ("clip", m.clips[0].clip_id) in got
    assert ("conn", 0) in got
    assert ("keep", m.clips[1].clip_id, False) in got


def test_trim_bar_emits_in_out():
    _app()
    from drama_shot_master.ui.widgets.compose.trim_bar import TrimBar
    bar = TrimBar()
    bar.set_clip(duration=10.0, in_point=None, out_point=None)
    got = []
    bar.trimChanged.connect(lambda i, o: got.append((i, o)))
    bar.set_in(1.5)
    bar.set_out(8.0)
    assert got[-1] == (1.5, 8.0)
    bar.set_in(9.0)         # 超过 out → 被夹到 out 之前
    assert bar.in_point() < bar.out_point()
