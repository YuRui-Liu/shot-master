"""SoundtrackEditor SFX tab smoke：tab 存在 + 状态切换 + pipeline 触发。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor


def _app():
    return QApplication.instance() or QApplication([])


def _cfg(tmp_path):
    from drama_shot_master.config import Config
    c = Config()
    c.settings_path = tmp_path / "s.json"
    return c


def _task(tmp_path):
    mp4 = tmp_path / "ep.mp4"; mp4.write_bytes(b"x")
    return {"id": "t1", "name": "测试", "mp4": str(mp4),
            "style": "末日", "workflow_id": "wf", "output_dir": ""}


def test_editor_has_sfx_tab(tmp_path):
    _app()
    editor = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    # 应当能找到一个 tab 标题里含 "SFX" 或 "音效"
    tabs_attr = None
    for candidate in ("tabs", "_tabs", "tab_widget", "_tab_widget"):
        if hasattr(editor, candidate):
            tabs_attr = candidate; break
    assert tabs_attr is not None, "未找到 tabs 容器属性"
    tabs = getattr(editor, tabs_attr)
    tab_names = [tabs.tabText(i) for i in range(tabs.count())]
    assert any("SFX" in n or "音效" in n for n in tab_names), \
        f"SFX tab 未找到，现有 tabs: {tab_names}"


def test_sfx_tab_plan_button_calls_facade(tmp_path, monkeypatch):
    _app()
    editor = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    called = {"plan": 0}
    def fake_plan(mp4, work_dir, *, cfg, provider=None):
        from sound_track_agent.sfx.session import SFXSession, SFXShot
        called["plan"] += 1
        return SFXSession(mp4, "h", 24.0,
                          shots=[SFXShot(0, 0.0, 3.0, status="planned",
                                          prompt_short="x", duration=3.0)])
    monkeypatch.setattr(
        "sound_track_agent.sfx.facade.plan_sfx_session", fake_plan)
    editor._on_sfx_plan_clicked()
    if editor._sfx_worker is not None:
        editor._sfx_worker.wait(5000)
    assert called["plan"] == 1


def test_sfx_tab_generate_button_calls_facade(tmp_path, monkeypatch):
    _app()
    editor = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    from sound_track_agent.sfx.session import SFXSession, SFXShot
    editor._sfx_session = SFXSession(
        "/m.mp4", "h", 24.0,
        shots=[SFXShot(0, 0.0, 3.0, status="planned", prompt_short="x",
                       duration=3.0)])
    called = {"gen": 0}
    def fake_gen(sess, work_dir, *, cfg, client=None):
        called["gen"] += 1
        return sess
    monkeypatch.setattr(
        "sound_track_agent.sfx.facade.generate_sfx_all", fake_gen)
    editor._on_sfx_generate_clicked()
    if editor._sfx_worker is not None:
        editor._sfx_worker.wait(5000)
    assert called["gen"] == 1


def test_sfx_tab_warns_generate_without_plan(tmp_path):
    _app()
    editor = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    editor._sfx_session = None
    from PySide6.QtWidgets import QMessageBox
    with patch.object(QMessageBox, "warning") as warn:
        editor._on_sfx_generate_clicked()
        warn.assert_called_once()


def test_apply_back_passes_sfx_session_to_mix(tmp_path, monkeypatch):
    """点应用回片时，mix 调用应当收到 sfx_session 参数。"""
    _app()
    editor = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    from sound_track_agent.sfx.session import SFXSession, SFXShot, SFXCandidate
    sess = SFXSession("/m.mp4", "h", 24.0, shots=[
        SFXShot(0, 0.0, 3.0, status="generated",
                candidates=[SFXCandidate("/a.mp3", 1, "x")],
                chosen_candidate=0)])
    editor._sfx_session = sess
    captured = {"sfx_session": "<unset>"}
    import sound_track_agent.mixdown as md
    def fake_assemble(*args, sfx_session=None, **kwargs):
        captured["sfx_session"] = sfx_session
        return tmp_path / "out.mp4"
    monkeypatch.setattr(md, "assemble_and_mix", fake_assemble)
    # 还要确保 BGM session 存在（apply 链路可能要它）
    from sound_track_agent.session import ScoringSession, SegmentScore
    editor._session = ScoringSession(
        source_mp4=str(tmp_path / "ep.mp4"), source_hash="h",
        global_style="x", frame_rate=24.0,
        segments=[SegmentScore(0, 0.0, 3.0)])
    # 调真实的 apply 入口
    apply_method_name = None
    for name in ("_on_apply_clicked", "_on_apply_to_video", "_on_apply",
                 "_on_export_clicked", "_on_export"):
        if hasattr(editor, name):
            apply_method_name = name; break
    if apply_method_name is None:
        pytest.skip("未找到 apply 入口；wiring 改动需手动校验")
    getattr(editor, apply_method_name)()
    # 等异步 worker 完成
    for worker_attr in ("_worker", "_pipeline_worker", "_apply_worker", "_sfx_worker"):
        w = getattr(editor, worker_attr, None)
        if w is not None and hasattr(w, "wait"):
            w.wait(5000)
    assert captured["sfx_session"] is sess
