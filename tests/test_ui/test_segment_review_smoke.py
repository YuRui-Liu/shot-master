import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.segment_review_widget import SegmentReviewWidget
from sound_track_agent.session import ScoringSession, SegmentScore, BGMCandidate


def _app():
    return QApplication.instance() or QApplication([])


def _sess():
    s0 = SegmentScore(index=0, t_start=0.0, t_end=4.0)
    s0.candidates = [BGMCandidate(path="/a.wav", seed=1, prompt="t"),
                     BGMCandidate(path="/b.wav", seed=2, prompt="t")]
    s1 = SegmentScore(index=1, t_start=4.0, t_end=8.0)
    s1.candidates = [BGMCandidate(path="/c.wav", seed=1, prompt="t")]
    return ScoringSession(source_mp4="/x", source_hash="h", global_style="s",
                          frame_rate=24.0, segments=[s0, s1])


def test_review_renders_one_card_per_segment():
    _app()
    w = SegmentReviewWidget(_sess())
    assert w.segment_card_count() == 2


def test_review_choose_sets_chosen_and_emits():
    _app()
    sess = _sess()
    w = SegmentReviewWidget(sess)
    seen = []
    w.chosenChanged.connect(lambda: seen.append(1))
    w.choose(0, 1)
    assert sess.segments[0].chosen_candidate == 1
    assert seen


def test_review_all_chosen_flag():
    _app()
    sess = _sess()
    w = SegmentReviewWidget(sess)
    assert w.all_chosen() is False
    w.choose(0, 0); w.choose(1, 0)
    assert w.all_chosen() is True


def test_review_regenerate_emits_index():
    _app()
    w = SegmentReviewWidget(_sess())
    seen = []
    w.regenerateRequested.connect(seen.append)
    w.request_regenerate(1)
    assert seen == [1]
