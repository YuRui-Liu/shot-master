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


def test_inspector_emits_override_and_lock():
    _app()
    from drama_shot_master.ui.widgets.compose.transition_inspector import TransitionInspector
    insp = TransitionInspector()
    insp.set_connector(index=0, effect="dissolve", duration=0.5, source="auto", locked=False)
    got = []
    insp.changed.connect(lambda idx, eff, dur, locked: got.append((idx, eff, dur, locked)))
    insp.set_effect("smoothleft")
    insp.set_duration(0.8)
    insp.set_locked(True)
    assert got[-1][0] == 0
    assert got[-1][1] == "smoothleft"
    assert got[-1][2] == 0.8
    assert got[-1][3] is True


def test_compose_panel_instantiates_and_loads_dir(tmp_path):
    _app()
    from drama_shot_master.config import load_config
    from drama_shot_master.ui.panels.compose_panel import ComposePanel
    cfg = load_config()
    panel = ComposePanel(cfg, payload={"clips": []})
    f1 = tmp_path / "a.mp4"; f1.write_bytes(b"x")
    f2 = tmp_path / "b.mp4"; f2.write_bytes(b"x")
    panel.add_clips([str(f1), str(f2)])
    assert len(panel.model().clips) == 2
    assert hasattr(panel, "renderRequested")
    assert hasattr(panel, "sendToSoundtrack")
    assert hasattr(panel, "dirty")
    assert hasattr(panel, "to_payload")


def test_compose_manager_smoke():
    _app()
    from drama_shot_master.core.compose_task_store import ComposeTaskStore
    from drama_shot_master.ui.panels.compose_task_manager_panel import ComposeTaskManagerPanel
    store = ComposeTaskStore()
    store.add("A", {"clips": []})
    mgr = ComposeTaskManagerPanel(store, on_persist=lambda: None)
    assert hasattr(mgr, "taskSelected")
    assert mgr.get_status(store.all()[0].id) in ("空闲", "生成中", "完成", "失败")
    mgr.refresh()  # must not crash
