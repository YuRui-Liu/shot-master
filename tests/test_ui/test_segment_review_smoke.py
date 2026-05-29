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


def test_player_is_lazy_not_created_on_init():
    _app()
    w = SegmentReviewWidget(_sess())
    assert w._player is None          # 构造时不碰音频后端（避免 headless 卡顿/segfault）
    assert hasattr(w, "seek") and hasattr(w, "play_btn")   # 共享 seek bar 存在


def test_missing_file_does_not_create_player(tmp_path, monkeypatch):
    _app()
    # 屏蔽模态警告框（offscreen 下模态 exec 会永久阻塞）
    import drama_shot_master.ui.widgets.segment_review_widget as m
    monkeypatch.setattr(m.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: None))
    w = SegmentReviewWidget(_sess())   # 候选路径 /a.wav 等都不存在
    w._on_candidate(0, 0)              # 文件缺失 → 选定 + 警告，但不建播放器
    assert w._session.segments[0].chosen_candidate == 0
    assert w._player is None


def test_segment_volume_slider_writes_session():
    _app()
    sess = _sess()
    w = SegmentReviewWidget(sess)
    seen = []
    w.segmentVolumeChanged.connect(lambda: seen.append(1))
    assert hasattr(w, "_vol_sliders") and len(w._vol_sliders) == 2
    w._vol_sliders[0].setValue(50)
    assert abs(sess.segments[0].volume - 0.5) < 1e-6 and seen


def test_volume_slider_syncs_to_audio_output():
    """拖音量滑条时，如果正在播该段候选，QAudioOutput.setVolume 应被同步调用。"""
    from unittest.mock import MagicMock
    _app()
    sess = _sess()
    w = SegmentReviewWidget(sess)
    # 模拟"当前正在播 seg0 候选 0"
    w._playing_key = (0, 0)
    w._audio = MagicMock()
    w._player = MagicMock()

    # 拖滑条到 50%
    w._on_volume(sess.segments[0], 50, MagicMock())
    w._audio.setVolume.assert_called_once_with(0.5)
    assert abs(sess.segments[0].volume - 0.5) < 1e-6


def test_volume_slider_not_called_when_not_playing_that_segment():
    """没在播该段时滑条事件不调 setVolume（避免影响其它段的播放）。"""
    from unittest.mock import MagicMock
    _app()
    sess = _sess()
    w = SegmentReviewWidget(sess)
    w._playing_key = (0, 0)              # 正在播 seg0
    w._audio = MagicMock()
    w._player = MagicMock()

    # 拖 seg1 的滑条
    w._on_volume(sess.segments[1], 80, MagicMock())
    w._audio.setVolume.assert_not_called()
    assert abs(sess.segments[1].volume - 0.8) < 1e-6  # 但 seg.volume 仍持久化
