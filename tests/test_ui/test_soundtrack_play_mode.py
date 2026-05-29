"""SoundtrackEditor 播放模式源解析：配乐/混音回退 + 无成片时不静默回退原声。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor


def _app():
    return QApplication.instance() or QApplication([])


def _cfg(tmp_path):
    from drama_shot_master.config import Config
    c = Config(); c.settings_path = tmp_path / "s.json"
    return c


def _editor(tmp_path, **task_over):
    mp4 = tmp_path / "raw.mp4"; mp4.write_bytes(b"x")
    task = {"id": "t1", "name": "t", "mp4": str(mp4),
            "style": "末日", "output_dir": str(tmp_path), "output": ""}
    task.update(task_over)
    return SoundtrackEditor(task, _cfg(tmp_path), tmp_path)


def test_bgm_mode_falls_back_to_task_output(tmp_path):
    """session.output 为空时，配乐模式应回退到 task['output']（已存在的 scored mp4）。"""
    _app()
    scored = tmp_path / "scored.mp4"; scored.write_bytes(b"v")
    ed = _editor(tmp_path, output=str(scored))
    ed._session = None
    ed._play_mode = "bgm"
    assert ed._resolve_video_source() == str(scored)


def test_bgm_mode_prefers_session_output(tmp_path):
    """session.output 存在时优先用它。"""
    _app()
    sess_out = tmp_path / "sess_scored.mp4"; sess_out.write_bytes(b"v")
    task_out = tmp_path / "task_scored.mp4"; task_out.write_bytes(b"v")
    ed = _editor(tmp_path, output=str(task_out))
    ed._session = type("S", (), {"output": str(sess_out)})()
    ed._play_mode = "bgm"
    assert ed._resolve_video_source() == str(sess_out)


def test_bgm_mode_returns_none_when_no_scored(tmp_path):
    """配乐模式无任何 scored mp4 时返回 None（不静默回退原声）。"""
    _app()
    ed = _editor(tmp_path, output="")
    ed._session = None
    ed._play_mode = "bgm"
    assert ed._resolve_video_source() is None


def test_raw_mode_returns_original_mp4(tmp_path):
    """原声模式始终返回原始 mp4。"""
    _app()
    ed = _editor(tmp_path, output="")
    ed._play_mode = "raw"
    assert ed._resolve_video_source() == ed._task["mp4"]
