"""overview_timeline_model: _Cue dataclass + derive_* 纯函数."""
from drama_shot_master.ui.widgets.overview_timeline_model import _Cue


def test_cue_fields():
    c = _Cue(track="bgm", t_start=0.0, t_end=3.0, label="末日", seg_index=0)
    assert c.track == "bgm"
    assert c.t_start == 0.0
    assert c.t_end == 3.0
    assert c.label == "末日"
    assert c.seg_index == 0


from drama_shot_master.ui.widgets.overview_timeline_model import (
    derive_video_cues, derive_bgm_cues, derive_sfx_cues,
    derive_dialogue_cues, derive_total_duration,
)


def test_derive_video_cues_from_shot_boundaries():
    cues = derive_video_cues([5.0, 12.0, 20.0], total_duration=30.0)
    # 切分: [0-5][5-12][12-20][20-30] = 4 段
    assert len(cues) == 4
    assert cues[0].t_start == 0.0 and cues[0].t_end == 5.0
    assert cues[1].t_start == 5.0 and cues[1].t_end == 12.0
    assert cues[3].t_end == 30.0
    assert all(c.track == "video" for c in cues)


def test_derive_video_cues_empty_boundaries_returns_single_block():
    cues = derive_video_cues([], total_duration=30.0)
    assert len(cues) == 1
    assert cues[0].t_start == 0.0 and cues[0].t_end == 30.0


def test_derive_video_cues_zero_duration_returns_empty():
    assert derive_video_cues([], total_duration=0.0) == []


def test_derive_bgm_cues_chosen_vs_unchosen_label():
    """chosen_candidate=None → label='(未选)'；否则 prompt 前 8 字."""
    from dataclasses import dataclass

    @dataclass
    class _Seg:
        t_start: float
        t_end: float
        chosen_candidate: object
        music_prompt: str
    sess = type("S", (), {"segments": [
        _Seg(0.0, 3.0, 0, "末日废土冷色调阴郁"),
        _Seg(3.0, 6.0, None, "古风"),
    ]})()
    cues = derive_bgm_cues(sess)
    assert len(cues) == 2
    assert cues[0].label == "末日废土冷色调阴郁"[:8]
    assert cues[1].label == "(未选)"
    assert all(c.track == "bgm" for c in cues)


def test_derive_bgm_cues_none_session():
    assert derive_bgm_cues(None) == []


def test_derive_sfx_cues_only_enabled_and_generated():
    """skipped / 未生成 / disabled 都过滤."""
    from dataclasses import dataclass

    @dataclass
    class _Shot:
        t_start: float
        duration: float
        prompt_short: str
        status: str = "generated"
        enabled: bool = True
    sess = type("S", (), {"shots": [
        _Shot(0.0, 3.0, "门吱呀", "generated", True),    # 应入
        _Shot(3.0, 3.0, "无", "skipped", True),          # 跳过
        _Shot(6.0, 2.0, "脚步", "generated", False),     # disabled 跳
        _Shot(8.0, 3.0, "雨", "planned", True),          # 未生成
    ]})()
    cues = derive_sfx_cues(sess)
    assert len(cues) == 1
    assert cues[0].label == "门吱呀"[:6]
    assert cues[0].t_start == 0.0 and cues[0].t_end == 3.0


def test_derive_dialogue_cues_from_timeline_dict():
    timeline = {"frame_rate": 24.0, "audios": [
        {"audio_path": "/a/voice_charA.flac",
         "start_frame": 0, "length_frames": 48},
        {"audio_path": "/a/voice_charB.flac",
         "start_frame": 72, "length_frames": 96},
    ]}
    cues = derive_dialogue_cues(timeline)
    assert len(cues) == 2
    assert abs(cues[0].t_start - 0.0) < 1e-6
    assert abs(cues[0].t_end - 2.0) < 1e-6           # 48/24
    assert abs(cues[1].t_start - 3.0) < 1e-6         # 72/24
    assert abs(cues[1].t_end - 7.0) < 1e-6           # (72+96)/24


def test_derive_dialogue_cues_empty_or_none():
    assert derive_dialogue_cues(None) == []
    assert derive_dialogue_cues({}) == []
    assert derive_dialogue_cues({"audios": []}) == []


def test_derive_total_duration_max_of_all():
    from dataclasses import dataclass

    @dataclass
    class _Seg:
        t_end: float

    @dataclass
    class _Shot:
        t_start: float
        duration: float
    bgm = type("B", (), {"segments": [_Seg(10.0), _Seg(20.0)]})()
    sfx = type("S", (), {"shots": [_Shot(15.0, 5.0)]})()
    timeline = {"frame_rate": 24.0, "audios": [
        {"start_frame": 0, "length_frames": 600},    # 25s
    ]}
    total = derive_total_duration(
        bgm_session=bgm, sfx_session=sfx,
        dialogue_audios=timeline, video_duration=22.0)
    assert total == 25.0    # 对白 25s 最长


def test_derive_total_duration_empty_falls_back_to_30():
    total = derive_total_duration(
        bgm_session=None, sfx_session=None,
        dialogue_audios=None, video_duration=0.0)
    assert total == 30.0
