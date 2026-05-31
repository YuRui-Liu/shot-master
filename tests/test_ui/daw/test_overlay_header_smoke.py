"""OverlayHeaderSection smoke: lane 行/折叠头重建 + 信号 emit."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.daw.overlay_header import OverlayHeaderSection


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _seg(kind, lane, t_start, t_end=0.0, volume=1.0, enabled=True):
    return SimpleNamespace(kind=kind, lane=lane, t_start=t_start, t_end=t_end,
                           volume=volume, enabled=enabled)


def _2bgm_1sfx():
    return [
        _seg("bgm", 0, 1.0),
        _seg("bgm", 1, 2.0),
        _seg("sfx", 0, 3.0),
    ]


def test_construct(app):
    w = OverlayHeaderSection()
    assert w is not None
    assert w.width() == 130


def test_expanded_three_lane_rows_and_head(app):
    w = OverlayHeaderSection()
    w.set_overlay(_2bgm_1sfx(), collapsed=False)
    assert len(w._lane_rows) == 3
    assert w.isVisible() or True  # 构造态不强制 show，仅校验未隐藏整体
    assert not w.isHidden()
    # lane 行可见（展开）
    for row in w._lane_rows:
        assert not row["widget"].isHidden()


def test_collapsed_hides_lane_rows(app):
    w = OverlayHeaderSection()
    w.set_overlay(_2bgm_1sfx(), collapsed=True)
    for row in w._lane_rows:
        assert row["widget"].isHidden()


def test_empty_hides_whole(app):
    w = OverlayHeaderSection()
    w.set_overlay([], collapsed=False)
    assert w.isHidden()


def test_collapse_head_emits(app):
    w = OverlayHeaderSection()
    w.set_overlay(_2bgm_1sfx(), collapsed=False)
    received = []
    w.collapseToggled.connect(lambda: received.append(True))
    w._head_btn.click()
    assert len(received) == 1


def test_lane_mute_emits(app):
    w = OverlayHeaderSection()
    w.set_overlay(_2bgm_1sfx(), collapsed=False)
    received = []
    w.laneMuteToggled.connect(lambda k, l, m: received.append((k, l, m)))
    row0 = w._lane_rows[0]  # ("bgm", 0)，初始未 checked
    row0["mute"].click()    # toggle → checked=True
    assert received[-1] == ("bgm", 0, True)


def test_lane_mute_kind_lane_payload(app):
    w = OverlayHeaderSection()
    w.set_overlay(_2bgm_1sfx(), collapsed=False)
    received = []
    w.laneMuteToggled.connect(lambda k, l, m: received.append((k, l, m)))
    row0 = w._lane_rows[0]  # ("bgm", 0)，初始未 checked
    row0["mute"].click()    # toggle → checked=True，emit (bgm,0,True)
    assert ("bgm", 0, True) in received


def test_lane_volume_emits(app):
    w = OverlayHeaderSection()
    w.set_overlay(_2bgm_1sfx(), collapsed=False)
    received = []
    w.laneVolumeChanged.connect(lambda k, l, v: received.append((k, l, v)))
    row0 = w._lane_rows[0]  # ("bgm", 0)
    row0["vol"].setValue(50)
    assert ("bgm", 0, 0.5) in received


def test_initial_aggregate_mute_and_volume(app):
    segs = [
        _seg("bgm", 0, 1.0, volume=0.8, enabled=True),
        _seg("bgm", 0, 5.0, volume=0.8, enabled=False),  # 任一 disabled → 行 M checked
        _seg("sfx", 0, 3.0, volume=0.6, enabled=True),
    ]
    w = OverlayHeaderSection()
    w.set_overlay(segs, collapsed=False)
    bgm_row = w._lane_rows[0]
    sfx_row = w._lane_rows[1]
    assert bgm_row["mute"].isChecked() is True
    assert bgm_row["vol"].value() == 80  # 首段 volume*100
    assert sfx_row["mute"].isChecked() is False
    assert sfx_row["vol"].value() == 60


def test_rebuild_clears_old_rows(app):
    w = OverlayHeaderSection()
    w.set_overlay(_2bgm_1sfx(), collapsed=False)
    assert len(w._lane_rows) == 3
    w.set_overlay([_seg("bgm", 0, 1.0)], collapsed=False)
    assert len(w._lane_rows) == 1
