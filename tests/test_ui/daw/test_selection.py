"""Selection model + _CueRef."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.daw.selection import _CueRef, Selection


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_curref_equality_and_hash():
    a = _CueRef(track="bgm", seg_index=0)
    b = _CueRef(track="bgm", seg_index=0)
    c = _CueRef(track="sfx", seg_index=0)
    assert a == b and hash(a) == hash(b)
    assert a != c


def test_selection_set_get(app):
    s = Selection()
    refs = [_CueRef("bgm", 0), _CueRef("sfx", 1)]
    s.set(refs)
    got = s.get()
    assert sorted(got, key=lambda r: (r.track, r.seg_index)) == \
           sorted(refs, key=lambda r: (r.track, r.seg_index))


def test_selection_toggle(app):
    s = Selection()
    r = _CueRef("bgm", 0)
    s.toggle(r)
    assert r in s.get()
    s.toggle(r)
    assert r not in s.get()


def test_selection_clear(app):
    s = Selection()
    s.set([_CueRef("bgm", 0), _CueRef("sfx", 0)])
    s.clear()
    assert s.get() == []


def test_selection_by_track(app):
    s = Selection()
    s.set([_CueRef("bgm", 0), _CueRef("bgm", 2), _CueRef("sfx", 1)])
    bt = s.by_track()
    assert sorted(bt["bgm"]) == [0, 2]
    assert bt["sfx"] == [1]


def test_selection_changed_signal_emitted(app):
    s = Selection()
    received = {"n": 0}
    s.changed.connect(lambda: received.__setitem__("n", received["n"] + 1))
    s.set([_CueRef("bgm", 0)])
    s.add(_CueRef("sfx", 0))
    s.toggle(_CueRef("bgm", 0))     # 移除
    s.clear()
    assert received["n"] == 4
