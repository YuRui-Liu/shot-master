"""验证 derive_dialogue_segments：从 cfg.video_tasks 按 mp4 路径匹配派生 DialogueSegment。"""
from drama_shot_master.core.dialogue_segment_deriver import derive_dialogue_segments
from sound_track_agent.session import DialogueSegment


class _FakeCfg:
    def __init__(self, video_tasks):
        self.video_tasks = video_tasks


def test_derive_returns_empty_when_no_match():
    cfg = _FakeCfg([{"last_result": "/x/other.mp4", "timeline": {}}])
    assert derive_dialogue_segments(cfg, "/x/ep.mp4") == []


def test_derive_returns_empty_when_no_video_tasks():
    cfg = _FakeCfg([])
    assert derive_dialogue_segments(cfg, "/x/ep.mp4") == []


def test_derive_returns_empty_when_cfg_has_no_attr():
    """cfg 没 video_tasks 属性也不抛。"""
    class _Bare: pass
    assert derive_dialogue_segments(_Bare(), "/x/ep.mp4") == []


def test_derive_matches_by_last_result_and_converts_frames():
    cfg = _FakeCfg([{
        "last_result": "/x/ep.mp4",
        "timeline": {
            "frame_rate": 24.0,
            "audios": [
                {"audio_id": "a1", "audio_path": "/x/d1.flac",
                 "start_frame": 0, "length_frames": 24},
                {"audio_id": "a2", "audio_path": "/x/d2.flac",
                 "start_frame": 48, "length_frames": 36},
            ],
        },
    }])
    segs = derive_dialogue_segments(cfg, "/x/ep.mp4")
    assert len(segs) == 2
    assert segs[0] == DialogueSegment(audio_path="/x/d1.flac",
                                       t_start=0.0, duration=1.0)
    assert segs[1] == DialogueSegment(audio_path="/x/d2.flac",
                                       t_start=2.0, duration=1.5)


def test_derive_first_match_wins_when_multiple_tasks():
    cfg = _FakeCfg([
        {"last_result": "/x/other.mp4", "timeline": {}},
        {"last_result": "/x/ep.mp4", "timeline": {
            "frame_rate": 30.0,
            "audios": [{"audio_path": "/x/d.flac",
                        "start_frame": 30, "length_frames": 60}]}},
        {"last_result": "/x/ep.mp4", "timeline": {}},   # 不应被命中
    ])
    segs = derive_dialogue_segments(cfg, "/x/ep.mp4")
    assert len(segs) == 1
    assert segs[0].t_start == 1.0
    assert segs[0].duration == 2.0


def test_derive_skips_audios_missing_audio_path():
    cfg = _FakeCfg([{
        "last_result": "/x/ep.mp4",
        "timeline": {"frame_rate": 24.0, "audios": [
            {"audio_path": "/x/d1.flac", "start_frame": 0, "length_frames": 24},
            {"audio_path": "", "start_frame": 24, "length_frames": 24},
            {"start_frame": 48, "length_frames": 24},
        ]},
    }])
    segs = derive_dialogue_segments(cfg, "/x/ep.mp4")
    assert len(segs) == 1
    assert segs[0].audio_path == "/x/d1.flac"


def test_derive_handles_zero_or_missing_frame_rate():
    """frame_rate=0 或缺 → fallback 24.0。"""
    cfg = _FakeCfg([{
        "last_result": "/x/ep.mp4",
        "timeline": {
            "audios": [{"audio_path": "/x/d.flac",
                        "start_frame": 24, "length_frames": 48}],
        },
    }])
    segs = derive_dialogue_segments(cfg, "/x/ep.mp4")
    assert segs[0].t_start == 1.0
    assert segs[0].duration == 2.0


def test_derive_handles_missing_timeline_or_audios():
    cfg = _FakeCfg([{"last_result": "/x/ep.mp4"}])
    assert derive_dialogue_segments(cfg, "/x/ep.mp4") == []

    cfg = _FakeCfg([{"last_result": "/x/ep.mp4", "timeline": {}}])
    assert derive_dialogue_segments(cfg, "/x/ep.mp4") == []
