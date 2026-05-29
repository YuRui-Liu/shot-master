"""SfxReviewWidget 卡片列表 smoke + 信号联通 + 候选选定。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from sound_track_agent.sfx.session import SFXShot, SFXSession, SFXCandidate
from drama_shot_master.ui.widgets.sfx_review_widget import SfxReviewWidget


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _sess():
    return SFXSession("/m.mp4", "h", 24.0, shots=[
        SFXShot(0, 0.0, 3.0, prompt_short="开门", duration=3.0,
                status="generated", volume=0.8,
                candidates=[SFXCandidate("/a.mp3", 1, "开门 Length: 3 seconds"),
                            SFXCandidate("/b.mp3", 2, "开门 Length: 3 seconds")],
                chosen_candidate=0),
        SFXShot(1, 3.0, 6.0, status="skipped"),
        SFXShot(2, 6.0, 9.0, prompt_short="脚步", duration=3.0, status="planned"),
    ])


def test_widget_renders_one_card_per_shot(app):
    w = SfxReviewWidget(_sess())
    assert w.shot_card_count() == 3


def test_widget_emits_chosen_changed(app):
    sess = _sess()
    w = SfxReviewWidget(sess)
    received = {"count": 0}
    w.chosenChanged.connect(lambda: received.__setitem__("count", received["count"] + 1))
    w.choose(0, 1)         # 改 shot 0 chosen → 1
    assert sess.shots[0].chosen_candidate == 1
    assert received["count"] == 1


def test_widget_emits_regenerate_requested(app):
    w = SfxReviewWidget(_sess())
    captured = {"idx": None}
    w.regenerateRequested.connect(lambda i: captured.__setitem__("idx", i))
    w.request_regenerate(2)
    assert captured["idx"] == 2


def test_widget_emits_prompt_changed(app):
    sess = _sess()
    w = SfxReviewWidget(sess)
    captured = {"called": 0}
    w.shotEdited.connect(lambda: captured.__setitem__("called", captured["called"] + 1))
    w.set_prompt(0, "新描述")
    assert sess.shots[0].prompt_short == "新描述"
    assert captured["called"] == 1


def test_widget_volume_change_writes_shot(app):
    sess = _sess()
    w = SfxReviewWidget(sess)
    w.set_volume(0, 1.2)
    assert abs(sess.shots[0].volume - 1.2) < 1e-6
