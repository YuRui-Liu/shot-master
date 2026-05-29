import json
from drama_shot_master.config import Config


def test_accent_fields_default():
    c = Config()
    assert abs(c.accent_big_threshold - 0.7) < 1e-9
    assert abs(c.accent_snap_window - 0.6) < 1e-9


def test_accent_fields_persist(tmp_path):
    sp = tmp_path / "settings.json"
    c = Config(settings_path=sp)
    c.update_settings(accent_big_threshold=0.5, accent_snap_window=1.0)
    data = json.loads(sp.read_text(encoding="utf-8"))
    assert data["accent_big_threshold"] == 0.5
    assert data["accent_snap_window"] == 1.0
