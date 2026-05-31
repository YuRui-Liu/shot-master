import shutil
import pytest
from drama_shot_master.core import ffmpeg_locate as fl


def test_resolve_prefers_bundled(monkeypatch, tmp_path):
    exe = tmp_path / ("ffmpeg.exe")
    exe.write_text("x")
    monkeypatch.setattr(fl, "_bundled_dir", lambda: tmp_path)
    monkeypatch.setattr(fl.os, "name", "nt")
    assert fl.ffmpeg_path() == str(exe)


def test_resolve_falls_back_to_which(monkeypatch, tmp_path):
    monkeypatch.setattr(fl, "_bundled_dir", lambda: tmp_path)  # no exe inside
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/ffmpeg")
    assert fl.ffmpeg_path() == "/usr/bin/ffmpeg"


def test_missing_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(fl, "_bundled_dir", lambda: tmp_path)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(FileNotFoundError):
        fl.ffmpeg_path()
