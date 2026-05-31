"""OverlayGenWorker 单测：注入假 generate_overlay_clip，验证 finished/failed 信号。

不碰网络、不依赖真线程：直接调 run()，用 QSignalSpy 断言信号。
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path

import pytest
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.daw import overlay_gen_worker
from drama_shot_master.ui.widgets.daw.overlay_gen_worker import OverlayGenWorker


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _make_worker(**over):
    kw = dict(seg_id="ov_bgm_1", kind="bgm", prompt="紧张配乐",
              duration=8.0, work_dir="/tmp/wd", cfg=object())
    kw.update(over)
    return OverlayGenWorker(**kw)


def test_run_success_emits_finished(app, monkeypatch):
    """假 generate_overlay_clip 返回 Path → finished(seg_id, audio_path) 发。"""
    fake_path = Path("/tmp/wd/cache/bgm/abc.mp3")
    called = {}

    def fake_gen(kind, prompt, duration, *, work_dir, cfg, client=None):
        called.update(kind=kind, prompt=prompt, duration=duration,
                      work_dir=work_dir, cfg=cfg)
        return fake_path

    monkeypatch.setattr(overlay_gen_worker, "generate_overlay_clip", fake_gen)

    w = _make_worker()
    spy_ok = QSignalSpy(w.finished)
    spy_fail = QSignalSpy(w.failed)

    w.run()

    assert spy_ok.count() == 1
    assert spy_ok.at(0)[0] == "ov_bgm_1"
    assert spy_ok.at(0)[1] == str(fake_path)
    assert spy_fail.count() == 0
    # 透传参数正确
    assert called["kind"] == "bgm"
    assert called["prompt"] == "紧张配乐"
    assert called["duration"] == 8.0


def test_run_failure_emits_failed(app, monkeypatch):
    """generate_overlay_clip 抛异常 → failed(seg_id, err) 发，不外泄异常。"""
    def boom(kind, prompt, duration, *, work_dir, cfg, client=None):
        raise RuntimeError("RunningHub 超时")

    monkeypatch.setattr(overlay_gen_worker, "generate_overlay_clip", boom)

    w = _make_worker(seg_id="ov_sfx_9", kind="sfx")
    spy_ok = QSignalSpy(w.finished)
    spy_fail = QSignalSpy(w.failed)

    w.run()  # 不应抛

    assert spy_ok.count() == 0
    assert spy_fail.count() == 1
    assert spy_fail.at(0)[0] == "ov_sfx_9"
    assert "RunningHub 超时" in spy_fail.at(0)[1]


def test_worker_is_qrunnable(app):
    """worker 可被 QThreadPool 调度（QRunnable）。"""
    from PySide6.QtCore import QRunnable
    w = _make_worker()
    assert isinstance(w, QRunnable)
