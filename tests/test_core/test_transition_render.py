from drama_shot_master.core.composition_model import ReelClip, CompositionModel
from drama_shot_master.core import transition_render as tr


def _comp(durs, trans="dissolve", tdur=0.5):
    clips = []
    for i, d in enumerate(durs):
        clips.append(ReelClip.new(path=f"/c{i}.mp4", duration=d,
                                  user_transition=trans, user_duration=tdur))
    return CompositionModel(clips=clips, fps=30, width=1920, height=1080)


def test_effects_library_grouped_and_has_none():
    keys = {e["name"] for e in tr.XFADE_EFFECTS}
    assert "dissolve" in keys and "smoothleft" in keys and "none" in keys
    cats = {e["category"] for e in tr.XFADE_EFFECTS}
    assert {"universal", "directional", "creative", "cut"} <= cats


def test_offsets_use_measured_durations():
    offs = tr.compute_offsets([8.0, 10.0, 6.0], [0.5, 0.5])
    assert offs == [7.5, 17.0]


def test_build_args_contains_xfade_and_acrossfade():
    comp = _comp([8.0, 6.0], trans="smoothleft", tdur=0.6)
    args = tr.build_ffmpeg_args(comp, out_path="/out/x.mp4",
                                ffmpeg="ffmpeg", probe=lambda p: 8.0)
    fc = " ".join(args)
    assert "xfade=transition=smoothleft:duration=0.6" in fc
    assert "acrossfade=d=0.6" in fc
    assert "scale=1920:1080" in fc and "fps=30" in fc and "format=yuv420p" in fc
    assert args[0] == "ffmpeg" and args[-1] == "/out/x.mp4"


def test_single_kept_clip_no_transition_just_normalize():
    comp = _comp([8.0])
    args = tr.build_ffmpeg_args(comp, out_path="/out/x.mp4",
                               ffmpeg="ffmpeg", probe=lambda p: 8.0)
    fc = " ".join(args)
    assert "xfade" not in fc
    assert "scale=1920:1080" in fc


def test_none_transition_degrades_to_cut():
    comp = _comp([8.0, 6.0], trans="none", tdur=0.5)
    args = tr.build_ffmpeg_args(comp, out_path="/out/x.mp4",
                               ffmpeg="ffmpeg", probe=lambda p: 8.0)
    fc = " ".join(args)
    assert "xfade" not in fc
    assert "concat" in fc
