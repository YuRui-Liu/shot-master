import pytest
from sound_track_agent.segment_planner import (
    Shot, plan_segments, emotion_distance, _avg_emotion, cluster_by_emotion,
)
from sound_track_agent.session import EmotionTag


def _shots(durations):
    shots, t = [], 0.0
    for i, d in enumerate(durations):
        shots.append(Shot(index=i, t_start=t, t_end=t + d))
        t += d
    return shots


def _et(v=0.0, a=0.3, i=0.5, labels=None):
    return EmotionTag(labels=list(labels or []), valence=v, arousal=a, intensity=i)


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


# ===== emotion_distance（纯）=====

def test_emotion_distance_zero_when_equal():
    e = _et(0.0, 0.5, 0.5)
    assert emotion_distance(e, e) == 0.0


def test_emotion_distance_valence_single_dim():
    a = _et(v=-1.0, a=0.3, i=0.5)
    b = _et(v=1.0, a=0.3, i=0.5)
    assert abs(emotion_distance(a, b) - 1.0) < 1e-9


def test_emotion_distance_arousal_single_dim():
    a = _et(v=0.0, a=0.0, i=0.5)
    b = _et(v=0.0, a=0.5, i=0.5)
    assert abs(emotion_distance(a, b) - 0.5) < 1e-9


def test_emotion_distance_opposite_max():
    a = _et(v=-1.0, a=1.0, i=1.0)
    b = _et(v=1.0, a=0.0, i=0.0)
    assert abs(emotion_distance(a, b) - (3 ** 0.5)) < 1e-9


# ===== _avg_emotion（纯）=====

def test_avg_emotion_weighted_by_count():
    a = _et(v=1.0, a=0.3, i=0.5)
    b = _et(v=0.0, a=0.6, i=0.7)
    out = _avg_emotion(a, b, n_a=2, n_b=1)
    assert abs(out.valence - 2.0/3.0) < 1e-9
    assert abs(out.arousal - (0.3*2 + 0.6) / 3) < 1e-9
    assert abs(out.intensity - (0.5*2 + 0.7) / 3) < 1e-9


def test_avg_emotion_labels_union_sorted():
    a = _et(labels=["tense", "sad"])
    b = _et(labels=["tense", "calm"])
    out = _avg_emotion(a, b, n_a=1, n_b=1)
    assert out.labels == ["calm", "sad", "tense"]


# ===== cluster_by_emotion（纯）=====

def _shot(idx, dur=1.0):
    return Shot(index=idx, t_start=float(idx), t_end=float(idx) + dur)


def test_cluster_one_shot_one_segment():
    shots = [_shot(0)]
    emotions = [_et()]
    segs = cluster_by_emotion(shots, emotions, max_segments=5, merge_threshold=0.25)
    assert len(segs) == 1
    assert segs[0].shot_ids == [0]
    assert segs[0].status == "tagged"
    assert segs[0].emotion is not None


def test_cluster_all_identical_merges_to_one():
    # 6 个情绪完全相同的 shot，邻接距离始终 < threshold → 一路合并到 1 段
    shots = [_shot(i) for i in range(6)]
    emotions = [_et(v=0.0, a=0.3, i=0.5) for _ in range(6)]
    segs = cluster_by_emotion(shots, emotions, max_segments=5, merge_threshold=0.25)
    assert len(segs) == 1


def test_cluster_all_different_returns_min_of_shots_and_max():
    shots = [_shot(i) for i in range(3)]
    emotions = [_et(v=-1.0), _et(v=0.0), _et(v=1.0)]
    segs = cluster_by_emotion(shots, emotions, max_segments=5, merge_threshold=0.25)
    assert len(segs) == 3


def test_cluster_merges_most_similar_neighbor():
    shots = [_shot(i) for i in range(3)]
    same = _et(v=0.0, a=0.3, i=0.5)
    diff = _et(v=1.0, a=0.9, i=0.9)
    segs = cluster_by_emotion(shots, [same, same, diff], max_segments=2, merge_threshold=0.25)
    assert len(segs) == 2
    assert segs[0].shot_ids == [0, 1]
    assert segs[1].shot_ids == [2]


def test_cluster_max_segments_one_forces_full_merge():
    shots = [_shot(i) for i in range(4)]
    emotions = [_et(v=v) for v in [-1.0, 0.0, 0.5, 1.0]]
    segs = cluster_by_emotion(shots, emotions, max_segments=1, merge_threshold=0.25)
    assert len(segs) == 1
    assert segs[0].shot_ids == [0, 1, 2, 3]


def test_cluster_threshold_zero_only_obeys_max():
    shots = [_shot(i) for i in range(5)]
    emotions = [_et(v=v) for v in [-1.0, -0.5, 0.0, 0.5, 1.0]]
    segs = cluster_by_emotion(shots, emotions, max_segments=3, merge_threshold=0.0)
    assert len(segs) == 3


def test_cluster_raises_on_empty_shots():
    with pytest.raises(ValueError):
        cluster_by_emotion([], [], max_segments=5, merge_threshold=0.25)
