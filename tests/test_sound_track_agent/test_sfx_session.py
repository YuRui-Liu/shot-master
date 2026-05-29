"""SFXShot / SFXCandidate / SFXSession dataclasses + 持久化。"""
from pathlib import Path
from sound_track_agent.sfx.session import (
    SFXShot, SFXCandidate, SFXSession,
)


def test_sfxshot_default_status_pending():
    s = SFXShot(shot_index=0, t_start=0.0, t_end=3.0)
    assert s.status == "pending"
    assert s.candidates == []
    assert s.chosen_candidate is None
    assert s.enabled is True
    assert abs(s.volume - 1.0) < 1e-6
    assert s.next_seed == 1


def test_sfxshot_shot_duration_property():
    assert SFXShot(0, 1.0, 4.5).shot_duration == 3.5


def test_sfxsession_save_load_roundtrip(tmp_path):
    sess = SFXSession(
        source_mp4="/a/b.mp4", source_hash="h", frame_rate=24.0,
        shots=[
            SFXShot(0, 0.0, 3.0, prompt_short="开门",
                    duration=3.0, status="planned"),
            SFXShot(1, 3.0, 5.0, status="skipped"),
            SFXShot(2, 5.0, 8.0, prompt_short="脚步",
                    duration=3.0, status="generated",
                    candidates=[SFXCandidate(path="/x.mp3", seed=1,
                                              prompt="脚步声 Length: 3 seconds")],
                    chosen_candidate=0),
        ])
    p = tmp_path / "sfx_session.json"
    sess.save(p)
    loaded = SFXSession.load(p)
    assert loaded is not None
    assert loaded.source_mp4 == "/a/b.mp4"
    assert len(loaded.shots) == 3
    assert loaded.shots[0].prompt_short == "开门"
    assert loaded.shots[1].status == "skipped"
    assert loaded.shots[2].candidates[0].path == "/x.mp3"
    assert loaded.shots[2].chosen_candidate == 0


def test_sfxsession_load_returns_none_on_corrupt(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{this is not json", encoding="utf-8")
    assert SFXSession.load(p) is None


def test_sfxsession_load_returns_none_on_missing():
    assert SFXSession.load(Path("/nonexistent/sfx_session.json")) is None
