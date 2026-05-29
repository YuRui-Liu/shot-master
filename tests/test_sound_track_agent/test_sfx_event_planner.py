"""sfx/event_planner: LLM 多帧检测 → SFXShot 状态机。"""
from pathlib import Path
from unittest.mock import MagicMock
from sound_track_agent.sfx.session import SFXShot, SFXSession
from sound_track_agent.sfx.event_planner import plan_one_shot, plan_all


def _provider(raw_text: str):
    p = MagicMock()
    p.generate.return_value = raw_text
    return p


def test_plan_one_shot_needs_sfx_true(tmp_path):
    s = SFXShot(0, 0.0, 3.5)
    p = _provider('{"needs_sfx": true, "prompt_short": "门吱呀", "duration_hint": 3.5}')
    plan_one_shot(p, s, [tmp_path / "f.png"])
    assert s.status == "planned"
    assert s.prompt_short == "门吱呀"
    assert abs(s.duration - 3.5) < 1e-6


def test_plan_one_shot_needs_sfx_false_skipped(tmp_path):
    s = SFXShot(0, 0.0, 3.0)
    p = _provider('{"needs_sfx": false}')
    plan_one_shot(p, s, [tmp_path / "f.png"])
    assert s.status == "skipped"


def test_plan_one_shot_empty_prompt_skipped(tmp_path):
    s = SFXShot(0, 0.0, 3.0)
    p = _provider('{"needs_sfx": true, "prompt_short": "  "}')
    plan_one_shot(p, s, [tmp_path / "f.png"])
    assert s.status == "skipped"


def test_plan_one_shot_clamps_duration(tmp_path):
    s = SFXShot(0, 0.0, 30.0)
    p = _provider('{"needs_sfx": true, "prompt_short": "雨", "duration_hint": 99.0}')
    plan_one_shot(p, s, [tmp_path / "f.png"])
    assert s.duration == 15.0   # 上限 clamp

    s2 = SFXShot(0, 0.0, 0.5)
    p2 = _provider('{"needs_sfx": true, "prompt_short": "击", "duration_hint": 0.1}')
    plan_one_shot(p2, s2, [tmp_path / "f.png"])
    assert s2.duration == 1.0   # 下限 clamp


def test_plan_one_shot_malformed_json_skipped(tmp_path):
    s = SFXShot(0, 0.0, 3.0)
    p = _provider("not json at all {{")
    plan_one_shot(p, s, [tmp_path / "f.png"])
    assert s.status == "skipped"


def test_plan_one_shot_empty_frames_skipped():
    s = SFXShot(0, 0.0, 3.0)
    p = _provider('{"needs_sfx": true, "prompt_short": "x"}')
    plan_one_shot(p, s, [])
    assert s.status == "skipped"
    p.generate.assert_not_called()


def test_plan_all_marks_session_planned(tmp_path):
    sess = SFXSession("/m.mp4", "h", 24.0, shots=[
        SFXShot(0, 0.0, 3.0),
        SFXShot(1, 3.0, 6.0),
    ])
    p = _provider('{"needs_sfx": true, "prompt_short": "x", "duration_hint": 3.0}')
    plan_all(sess, p, frames_provider=lambda s, n: [tmp_path / "f.png"])
    assert sess.sfx_planned is True
    assert all(s.status == "planned" for s in sess.shots)


def test_plan_all_skips_already_processed(tmp_path):
    """非 pending 的 shot 不动。"""
    sess = SFXSession("/m.mp4", "h", 24.0, shots=[
        SFXShot(0, 0.0, 3.0, status="generated", prompt_short="已有"),
        SFXShot(1, 3.0, 6.0),
    ])
    p = _provider('{"needs_sfx": true, "prompt_short": "新", "duration_hint": 3.0}')
    plan_all(sess, p, frames_provider=lambda s, n: [tmp_path / "f.png"])
    assert sess.shots[0].prompt_short == "已有"   # 未被覆盖
    assert sess.shots[1].status == "planned"
