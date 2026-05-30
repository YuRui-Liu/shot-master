"""TrackMixState：mute/solo/volume + 独奏解算 + mix.json 持久化。"""
from drama_shot_master.ui.widgets.daw.track_mix import (
    TrackMixState, load_mix, save_mix, TRACKS)


def test_tracks_are_three_audio_tracks():
    assert TRACKS == ("video", "bgm", "sfx")


def test_default_all_audible_full_volume():
    m = TrackMixState()
    for t in TRACKS:
        assert m.is_muted(t) is False
        assert m.is_soloed(t) is False
        assert m.volume(t) == 1.0
        assert m.audible(t) is True


def test_mute_makes_inaudible():
    m = TrackMixState()
    m.set_muted("bgm", True)
    assert m.audible("bgm") is False
    assert m.audible("video") is True


def test_solo_silences_others():
    m = TrackMixState()
    m.set_soloed("bgm", True)
    assert m.audible("bgm") is True
    assert m.audible("video") is False
    assert m.audible("sfx") is False


def test_multi_solo():
    m = TrackMixState()
    m.set_soloed("bgm", True)
    m.set_soloed("sfx", True)
    assert m.audible("bgm") is True and m.audible("sfx") is True
    assert m.audible("video") is False


def test_muted_solo_track_still_inaudible():
    m = TrackMixState()
    m.set_soloed("bgm", True)
    m.set_muted("bgm", True)
    assert m.audible("bgm") is False


def test_volume_clamped():
    m = TrackMixState()
    m.set_volume("bgm", 2.0); assert m.volume("bgm") == 1.5
    m.set_volume("bgm", -1.0); assert m.volume("bgm") == 0.0


def test_effective_volume_zero_when_inaudible():
    m = TrackMixState()
    m.set_volume("bgm", 1.2)
    assert m.effective_volume("bgm") == 1.2
    m.set_muted("bgm", True)
    assert m.effective_volume("bgm") == 0.0


def test_to_from_dict_roundtrip():
    m = TrackMixState()
    m.set_muted("bgm", True); m.set_soloed("sfx", True); m.set_volume("video", 0.5)
    m2 = TrackMixState.from_dict(m.to_dict())
    assert m2.is_muted("bgm") and m2.is_soloed("sfx") and m2.volume("video") == 0.5


def test_save_load_roundtrip(tmp_path):
    m = TrackMixState(); m.set_muted("sfx", True); m.set_volume("bgm", 0.8)
    save_mix(tmp_path, m)
    m2 = load_mix(tmp_path)
    assert m2.is_muted("sfx") and m2.volume("bgm") == 0.8


def test_load_missing_returns_default(tmp_path):
    m = load_mix(tmp_path)
    assert all(m.audible(t) for t in TRACKS)


def test_load_corrupt_returns_default(tmp_path):
    (tmp_path / "mix.json").write_text("{bad json", encoding="utf-8")
    m = load_mix(tmp_path)
    assert all(m.audible(t) for t in TRACKS)
