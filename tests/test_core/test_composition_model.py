from drama_shot_master.core.composition_model import ReelClip, CompositionModel


def _clip(**kw):
    d = dict(path="/a.mp4", duration=8.0)
    d.update(kw)
    return ReelClip.new(**d)


def test_new_clip_has_id_and_defaults():
    c = _clip()
    assert c.clip_id
    assert c.keep is True
    assert c.in_point is None and c.out_point is None
    assert c.locked is False
    assert c.cv_scores == {}


def test_effective_prefers_user_then_auto_then_default():
    c = _clip(auto_transition="smoothleft", auto_duration=0.6)
    assert c.effective_transition() == "smoothleft"
    assert c.effective_duration() == 0.6
    c.user_transition = "dissolve"
    c.user_duration = 0.9
    assert c.effective_transition() == "dissolve"
    assert c.effective_duration() == 0.9
    d = _clip()
    assert d.effective_transition() == "dissolve"
    assert d.effective_duration() == 0.5


def test_trimmed_duration():
    c = _clip(duration=10.0, in_point=1.5, out_point=8.0)
    assert c.trimmed_duration() == 6.5
    assert _clip(duration=10.0).trimmed_duration() == 10.0


def test_kept_clips_preserves_order_and_filters_dropped():
    m = CompositionModel(clips=[_clip(path="/0.mp4"), _clip(path="/1.mp4"), _clip(path="/2.mp4")])
    m.clips[1].keep = False
    kept = m.kept_clips()
    assert [c.path for c in kept] == ["/0.mp4", "/2.mp4"]


def test_reorder_clips():
    m = CompositionModel(clips=[_clip(path="/0.mp4"), _clip(path="/1.mp4")])
    ids = [m.clips[1].clip_id, m.clips[0].clip_id]
    m.reorder_clips(ids)
    assert [c.path for c in m.clips] == ["/1.mp4", "/0.mp4"]


def test_update_clip():
    m = CompositionModel(clips=[_clip()])
    cid = m.clips[0].clip_id
    m.update_clip(cid, keep=False, user_transition="fade")
    assert m.clips[0].keep is False
    assert m.clips[0].user_transition == "fade"


def test_validate_requires_at_least_one_kept():
    m = CompositionModel(clips=[_clip()])
    m.clips[0].keep = False
    ok, msg = m.validate()
    assert ok is False and "保留" in msg


def test_validate_flags_segment_shorter_than_transition():
    a = _clip(path="/0.mp4", duration=0.4, user_transition="dissolve", user_duration=0.5)
    b = _clip(path="/1.mp4", duration=5.0)
    m = CompositionModel(clips=[a, b])
    ok, msg = m.validate()
    assert ok is True
    assert "硬切" in msg or "降级" in msg


def test_to_from_dict_roundtrip():
    m = CompositionModel(clips=[_clip(in_point=1.0), _clip(path="/1.mp4")], fps=30, width=1920, height=1080)
    m.clips[0].user_transition = "wipeleft"
    d = m.to_dict()
    m2 = CompositionModel.from_dict(d)
    assert m2.fps == 30 and m2.width == 1920
    assert [c.path for c in m2.clips] == ["/a.mp4", "/1.mp4"]
    assert m2.clips[0].in_point == 1.0
    assert m2.clips[0].user_transition == "wipeleft"
