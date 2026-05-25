import pytest
from sound_track_agent.segment_planner import Shot, plan_segments


def _shots(durations):
    shots, t = [], 0.0
    for i, d in enumerate(durations):
        shots.append(Shot(index=i, t_start=t, t_end=t + d))
        t += d
    return shots


def test_plan_segments_aggregates_to_target_count():
    shots = _shots([2, 2, 2, 2, 2, 2, 2, 2])   # 8 镜头，总 16s
    segs = plan_segments(shots, target=4)
    assert len(segs) == 4
    assert segs[0].t_start == 0.0
    assert segs[-1].t_end == 16.0
    for a, b in zip(segs, segs[1:]):
        assert a.t_end == b.t_start
    all_ids = [i for s in segs for i in s.shot_ids]
    assert sorted(all_ids) == list(range(8))


def test_plan_segments_clamps_when_few_shots():
    shots = _shots([3, 3])
    segs = plan_segments(shots, target=4)
    assert len(segs) == 2
    assert all(s.status == "pending" for s in segs)


def test_plan_segments_index_sequential():
    shots = _shots([1, 1, 1, 1, 1, 1])
    segs = plan_segments(shots, target=3)
    assert [s.index for s in segs] == [0, 1, 2]


def test_plan_segments_empty_raises():
    with pytest.raises(ValueError):
        plan_segments([], target=4)
