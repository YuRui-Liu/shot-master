"""SoundtrackEditor 框选生成接线（子项目 #3d-D7）。

mock 重组件 / 用 tmp work_dir，绝不真连网络：
- monkeypatch GenerateOverlayDialog（exec 返回 Accepted + result_value 返回 (kind,prompt) 或 None）；
- monkeypatch OverlayGenWorker（记录构造 + 不真起线程）；
- 框选 → dialog 返回 ("bgm","p") → _overlay_session 多一个 status=="generating" 段
  + save_overlay 落盘 + worker 被起 + finished/failed 已连；
- dialog 返回 None（取消）→ 无 add、无 worker；
- finished 槽 → seg.audio_path/status="generated" + mix_engine.set_segments 被调 + 刷新；
- failed 槽 → seg.status="failed" + 刷新；
- finished/failed 对已删 seg → 丢弃不崩。
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication, QDialog

import drama_shot_master.ui.widgets.soundtrack_editor as se_mod
from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor


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


class _FakeDialog:
    """替身 GenerateOverlayDialog：exec 返回 Accepted，result_value 可控。"""
    last = None

    def __init__(self, t_start, t_end, *, suggest_fn=None, parent=None):
        self.t_start = t_start
        self.t_end = t_end
        self.suggest_fn = suggest_fn
        _FakeDialog.last = self

    def exec(self):
        return QDialog.Accepted if self._accept else QDialog.Rejected

    def result_value(self):
        return self._value


def _make_dialog_factory(value, accept=True):
    def factory(t_start, t_end, *, suggest_fn=None, parent=None):
        d = _FakeDialog(t_start, t_end, suggest_fn=suggest_fn, parent=parent)
        d._accept = accept
        d._value = value
        return d
    return factory


class _FakeWorker:
    """替身 OverlayGenWorker：记录构造，提供 finished/failed 假信号，不起线程。"""
    instances = []

    def __init__(self, seg_id, kind, prompt, duration, work_dir, cfg, *,
                 client=None, parent=None):
        self.seg_id = seg_id
        self.kind = kind
        self.prompt = prompt
        self.duration = duration
        self.work_dir = work_dir
        self.cfg = cfg
        self.finished = _FakeSignal()
        self.failed = _FakeSignal()
        self.started = False
        _FakeWorker.instances.append(self)


class _FakeSignal:
    def __init__(self):
        self._slots = []

    def connect(self, fn):
        self._slots.append(fn)

    def emit(self, *args):
        for fn in list(self._slots):
            fn(*args)


def _patch_components(monkeypatch, dialog_value, accept=True):
    """打桩 dialog + worker + threadpool（不真起线程），返回 _FakeWorker 类。"""
    _FakeWorker.instances = []
    monkeypatch.setattr(se_mod, "GenerateOverlayDialog",
                        _make_dialog_factory(dialog_value, accept), raising=False)
    monkeypatch.setattr(se_mod, "OverlayGenWorker", _FakeWorker, raising=False)
    return _FakeWorker


def test_gen_overlay_id_unique_and_prefixed(tmp_path):
    _app()
    ed = _ed(tmp_path)
    a = ed._gen_overlay_id("bgm")
    b = ed._gen_overlay_id("bgm")
    assert a.startswith("ov_bgm_")
    assert ed._gen_overlay_id("sfx").startswith("ov_sfx_")
    assert a != b


def test_rubber_band_accept_adds_placeholder_and_starts_worker(tmp_path, monkeypatch):
    _app()
    _patch_components(monkeypatch, ("bgm", "紧张配乐"))
    ed = _ed(tmp_path)
    # 框选区间 → _x_to_t 受控
    ed._track_view._x_to_t = lambda x: float(x)
    saved = []
    monkeypatch.setattr(se_mod, "save_overlay",
                        lambda wd, sess: saved.append((wd, sess)), raising=False)
    refreshed = []
    ed._refresh_overlay_view = lambda: refreshed.append(1)

    n_before = len(ed._overlay_session.segments)
    # QRect(x=2,w=6) → left=2, right=x+w-1=7（Qt 语义）→ [2,7]
    ed._on_rubber_band(QRect(2, 0, 6, 10), None)

    segs = ed._overlay_session.segments
    assert len(segs) == n_before + 1
    new = segs[-1]
    assert new.kind == "bgm"
    assert new.prompt == "紧张配乐"
    assert new.status == "generating"
    assert abs(new.t_start - 2.0) < 1e-6 and abs(new.t_end - 7.0) < 1e-6
    assert saved, "save_overlay 应被调用落盘占位"
    assert refreshed, "占位应立即刷新"
    # worker 被起且连了 finished/failed
    assert _FakeWorker.instances, "应起一个 OverlayGenWorker"
    w = _FakeWorker.instances[-1]
    assert w.seg_id == new.id
    assert w.kind == "bgm"
    assert w.finished._slots and w.failed._slots
    # 编辑器持引用防 GC
    assert w in getattr(ed, "_overlay_workers", [])


def test_rubber_band_cancel_no_add_no_worker(tmp_path, monkeypatch):
    _app()
    _patch_components(monkeypatch, None, accept=False)
    ed = _ed(tmp_path)
    ed._track_view._x_to_t = lambda x: float(x)
    n_before = len(ed._overlay_session.segments)
    ed._on_rubber_band(QRect(2, 0, 6, 10), None)
    assert len(ed._overlay_session.segments) == n_before
    assert not _FakeWorker.instances


def test_rubber_band_result_none_no_add(tmp_path, monkeypatch):
    """accept 但 result_value 返回 None → 同取消处理。"""
    _app()
    _patch_components(monkeypatch, None, accept=True)
    ed = _ed(tmp_path)
    ed._track_view._x_to_t = lambda x: float(x)
    n_before = len(ed._overlay_session.segments)
    ed._on_rubber_band(QRect(2, 0, 6, 10), None)
    assert len(ed._overlay_session.segments) == n_before
    assert not _FakeWorker.instances


def test_finished_slot_updates_seg_and_mix(tmp_path, monkeypatch):
    _app()
    ed = _ed(tmp_path)
    seg = ed._overlay_session.add("bgm", 0.0, 5.0, "p", seg_id="ov1",
                                  status="generating")
    set_seg_calls = []
    ed._mix_engine.set_segments = lambda segs: set_seg_calls.append(segs)
    saved = []
    monkeypatch.setattr(se_mod, "save_overlay",
                        lambda wd, sess: saved.append(sess), raising=False)
    refreshed = []
    ed._refresh_overlay_view = lambda: refreshed.append(1)

    ed._on_overlay_gen_finished("ov1", "C:/out/ov1.mp3")

    assert seg.audio_path == "C:/out/ov1.mp3"
    assert seg.status == "generated"
    assert saved
    assert set_seg_calls and set_seg_calls[-1] == ed._overlay_session.segments
    assert refreshed


def test_finished_slot_missing_seg_discarded(tmp_path, monkeypatch):
    _app()
    ed = _ed(tmp_path)
    set_seg_calls = []
    ed._mix_engine.set_segments = lambda segs: set_seg_calls.append(segs)
    # 不抛即可
    ed._on_overlay_gen_finished("nope", "C:/x.mp3")


def test_failed_slot_marks_failed_and_refreshes(tmp_path, monkeypatch):
    _app()
    ed = _ed(tmp_path)
    seg = ed._overlay_session.add("sfx", 1.0, 3.0, "boom", seg_id="ov2",
                                  status="generating")
    saved = []
    monkeypatch.setattr(se_mod, "save_overlay",
                        lambda wd, sess: saved.append(sess), raising=False)
    refreshed = []
    ed._refresh_overlay_view = lambda: refreshed.append(1)

    ed._on_overlay_gen_failed("ov2", "RunningHub timeout")

    assert seg.status == "failed"
    assert saved
    assert refreshed


def test_failed_slot_missing_seg_no_raise(tmp_path):
    _app()
    ed = _ed(tmp_path)
    ed._on_overlay_gen_failed("nope", "err")   # 不抛即可


def test_retry_overlay_restarts_worker(tmp_path, monkeypatch):
    """失败片段重试：复用 prompt/区间重起 worker，status→generating。"""
    _app()
    _FakeWorker.instances = []
    monkeypatch.setattr(se_mod, "OverlayGenWorker", _FakeWorker, raising=False)
    ed = _ed(tmp_path)
    seg = ed._overlay_session.add("bgm", 0.0, 5.0, "p", seg_id="ov3",
                                  status="failed")
    refreshed = []
    ed._refresh_overlay_view = lambda: refreshed.append(1)

    ed._retry_overlay_segment("ov3")

    assert seg.status == "generating"
    assert _FakeWorker.instances
    w = _FakeWorker.instances[-1]
    assert w.seg_id == "ov3"
    assert w.kind == "bgm"
    assert w.prompt == "p"
    assert refreshed
