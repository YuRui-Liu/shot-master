"""配乐叠加播放：暖缓存切模式要 resync+resume（Bug1）+ 构建完按当前模式应用（Q2）。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
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


def test_sync_overlay_to_video_seeks_live_pos_and_plays(tmp_path):
    """_sync_overlay_to_video：seek 到视频实时位置 + 视频在播则 overlay.play。"""
    _app()
    ed = _ed(tmp_path)
    calls = []
    ed._overlay.seek = lambda t: calls.append(("seek", t))
    ed._overlay.play = lambda: calls.append(("play",))
    ed._video_preview.position = lambda: 12.5
    ed._video_preview.is_playing = lambda: True
    ed._sync_overlay_to_video()
    assert ("seek", 12.5) in calls
    assert ("play",) in calls


def test_sync_overlay_does_not_play_when_video_paused(tmp_path):
    _app()
    ed = _ed(tmp_path)
    calls = []
    ed._overlay.seek = lambda t: calls.append("seek")
    ed._overlay.play = lambda: calls.append("play")
    ed._video_preview.position = lambda: 3.0
    ed._video_preview.is_playing = lambda: False
    ed._sync_overlay_to_video()
    assert "seek" in calls and "play" not in calls


def test_warm_cache_path_resyncs(tmp_path):
    """指纹未变的暖缓存路径切到配乐：应调 _sync_overlay_to_video（不再静默）。"""
    _app()
    from sound_track_agent.session import ScoringSession, SegmentScore, BGMCandidate
    mp3 = tmp_path / "a.mp3"; mp3.write_bytes(b"x")
    ed = _ed(tmp_path)
    ed._session = ScoringSession(source_mp4="", source_hash="", global_style="x",
        frame_rate=24.0, segments=[SegmentScore(0, 0.0, 5.0,
            candidates=[BGMCandidate(path=str(mp3), seed=1, prompt="p")],
            chosen_candidate=0)])
    # 预置暖缓存：bgm 轨已载入 + 指纹匹配
    ed._overlay.set_track("bgm", str(mp3))
    ed._preview_fp["bgm"] = ed._preview_fingerprint("bgm")
    synced = []
    ed._sync_overlay_to_video = lambda: synced.append(True)
    ed._ensure_preview_tracks("bgm")
    assert synced == [True]
    assert ed._overlay.is_enabled("bgm") is True


def test_preview_built_applies_current_mode_not_stale(tmp_path):
    """构建完成时按当前 _play_mode 应用（用户在构建中改了模式）。"""
    _app()
    ed = _ed(tmp_path)
    mp3 = tmp_path / "a.mp3"; mp3.write_bytes(b"x")
    ed._overlay.set_track("bgm", str(mp3))
    ed._overlay.set_track("sfx", str(mp3))
    ed._play_mode = "mix"           # 用户最终停在 mix
    ed._sync_overlay_to_video = lambda: None
    # 构建结果里 mode 是旧的 "bgm"
    ed._on_preview_built({"bgm": str(mp3), "sfx": str(mp3),
                          "bgm_fp": "x", "sfx_fp": "y", "mode": "bgm"})
    # 应按当前 mix 应用 → sfx 也启用
    assert ed._overlay.is_enabled("sfx") is True
