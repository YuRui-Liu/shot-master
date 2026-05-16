from pathlib import Path
from PIL import Image
import pytest
from app.config import load_config
from app.ui.state import AppState, restore_from_config, remember_dirs


def _mk_imgs(folder: Path, n=3):
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        Image.new("RGB", (40, 40), (i * 40 % 256, 100, 100)).save(folder / f"i{i}.png")


def test_appstate_defaults():
    s = AppState()
    assert s.current_dir is None
    assert s.images == []
    assert s.selected == []
    assert s.output_dir is None
    assert s.active_function == "inference"


def test_load_dir_populates_images(tmp_path):
    folder = tmp_path / "imgs"
    _mk_imgs(folder, 3)
    s = AppState()
    s.load_dir(folder)
    assert s.current_dir == folder
    assert len(s.images) == 3
    assert all(info.path.suffix == ".png" for info in s.images)


def test_load_missing_dir_clears(tmp_path):
    s = AppState()
    s.load_dir(tmp_path / "nope")
    assert s.current_dir is None
    assert s.images == []


def test_restore_from_config_existing(tmp_path):
    folder = tmp_path / "imgs"
    _mk_imgs(folder, 2)
    out = tmp_path / "out"
    out.mkdir()
    env = tmp_path / ".env"; env.write_text("DEFAULT_PROVIDER=doubao\n")
    sj = tmp_path / "s.json"
    cfg = load_config(env_path=env, settings_path=sj)
    cfg.update_settings(last_input_dir=str(folder), last_output_dir=str(out))
    s = AppState()
    restore_from_config(s, cfg)
    assert s.current_dir == folder
    assert len(s.images) == 2
    assert s.output_dir == out


def test_restore_from_config_stale_path_ignored(tmp_path):
    env = tmp_path / ".env"; env.write_text("DEFAULT_PROVIDER=doubao\n")
    sj = tmp_path / "s.json"
    cfg = load_config(env_path=env, settings_path=sj)
    cfg.update_settings(last_input_dir=str(tmp_path / "gone"),
                        last_output_dir=str(tmp_path / "gone_out"))
    s = AppState()
    restore_from_config(s, cfg)
    assert s.current_dir is None
    assert s.images == []
    assert s.output_dir is None


def test_remember_dirs_writes_config(tmp_path):
    folder = tmp_path / "imgs"; _mk_imgs(folder, 1)
    out = tmp_path / "out"; out.mkdir()
    env = tmp_path / ".env"; env.write_text("DEFAULT_PROVIDER=doubao\n")
    sj = tmp_path / "s.json"
    cfg = load_config(env_path=env, settings_path=sj)
    s = AppState()
    s.current_dir = folder
    s.output_dir = out
    remember_dirs(s, cfg)
    import json as _j
    data = _j.loads(sj.read_text())
    assert data["last_input_dir"] == str(folder)
    assert data["last_output_dir"] == str(out)
