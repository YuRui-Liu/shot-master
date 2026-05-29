import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication, QWidget
from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor

_SKIP_4C = pytest.mark.skip(reason="Phase 4c: 4 tab 体系已被 DAW 替换")


def _app():
    return QApplication.instance() or QApplication([])


def _cfg(tmp_path):
    return type("C", (), {"soundtrack_workflow_id": "", "soundtrack_seeds_count": 2,
                          "soundtrack_output_dir": "", "video_output_dir": str(tmp_path),
                          "soundtrack_crossfade": 0.5, "accent_big_threshold": 0.7,
                          "accent_snap_window": 0.6})()


def _task():
    return {"id": "t1", "name": "EP01", "mp4": "/x/ep1.mp4",
            "style": "末日废土", "output_dir": "", "status": "空闲", "output": ""}


@_SKIP_4C
def test_editor_is_qwidget_with_three_tabs(tmp_path):
    _app()
    ed = SoundtrackEditor(_task(), _cfg(tmp_path), tmp_path)
    assert isinstance(ed, QWidget)
    # Phase 4a 新增 SFX tab → 现在是 4 个 tab；用 >= 3 保持 BGM 3 个基础 tab 契约
    assert ed.tabs.count() >= 3
    assert ed.style_edit.toPlainText() == "末日废土"


def test_editor_has_no_closed_signal():
    # widget 不需要 closed 信号 / closeEvent；浮出由 DetachedEditorWindow 承载
    assert not hasattr(SoundtrackEditor, "closed")


@_SKIP_4C
def test_to_payload_reads_widgets(tmp_path):
    _app()
    ed = SoundtrackEditor(_task(), _cfg(tmp_path), tmp_path)
    ed.mp4_edit.setText("/y/ep2.mp4")
    ed.style_edit.setPlainText("赛博霓虹")
    ed.out_edit.setText("/out/dir")
    p = ed.to_payload()
    assert p == {"mp4": "/y/ep2.mp4", "style": "赛博霓虹", "output_dir": "/out/dir"}


def test_output_base_falls_back(tmp_path):
    _app()
    ed = SoundtrackEditor(_task(), _cfg(tmp_path), tmp_path)
    assert "soundtrack" in str(ed._resolve_output_base())


def test_export_guard_no_mp4_does_not_crash(tmp_path, monkeypatch):
    _app()
    import drama_shot_master.ui.widgets.soundtrack_editor as m
    ed = SoundtrackEditor({"id": "t1", "name": "EP1", "mp4": "", "style": ""},
                          _cfg(tmp_path), tmp_path)
    monkeypatch.setattr(m.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(m.QMessageBox, "information", staticmethod(lambda *a, **k: None))
    assert hasattr(ed, "btn_export")
    ed._on_export()        # 无 mp4 → 走校验提示并 return，不崩


def test_preview_button_toggles_with_output(tmp_path, monkeypatch):
    _app()
    import drama_shot_master.ui.widgets.soundtrack_editor as m
    ed = SoundtrackEditor({"id": "t1", "name": "EP1", "mp4": "", "style": ""},
                          _cfg(tmp_path), tmp_path)
    assert ed.btn_preview.isEnabled() is False
    opened = []
    monkeypatch.setattr(m.QDesktopServices, "openUrl", lambda url: opened.append(url))
    fake = tmp_path / "clip_scored.mp4"; fake.write_bytes(b"x")
    ed._session = type("S", (), {"output": str(fake)})()
    ed._update_preview_enabled()
    assert ed.btn_preview.isEnabled() is True
    ed._on_preview()
    assert opened


@_SKIP_4C
def test_session_mount_does_not_crash(tmp_path):
    # 直接 smoke 测 _mount_session_tabs：给一个空 session（segments/accent_points 空），
    # 构造 ② 试听选优 / ③ 卡点 子控件不崩（不经 facade 真加载）。
    _app()
    stub = type("Sess", (), {"segments": [], "accent_points": [],
                             "source_mp4": "", "output": None})()
    ed = SoundtrackEditor(_task(), _cfg(tmp_path), tmp_path)
    ed._session = stub
    ed._mount_session_tabs()
    assert ed._review is not None and ed._accent is not None


# ---------------------------------------------------------------------------
# Task 7: dialogue_segments 派生接线 + 重排段落按钮
# ---------------------------------------------------------------------------

def test_editor_passes_derived_dialogue_segments_to_prepare(tmp_path, monkeypatch):
    """SoundtrackEditor 第一次跑 pipeline 时，应从 cfg.video_tasks 派生 dialogue_segments 并传给 prepare_session。"""
    _app()
    from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor
    from sound_track_agent.session import (
        ScoringSession, SegmentScore, DialogueSegment,
    )

    mp4 = tmp_path / "ep.mp4"; mp4.write_bytes(b"x")
    cfg = _cfg(tmp_path)
    cfg.video_tasks = [{
        "last_result": str(mp4),
        "timeline": {
            "frame_rate": 24.0,
            "audios": [{"audio_path": "/x/d.flac",
                        "start_frame": 0, "length_frames": 24}],
        }
    }]

    captured = {"dialogue_segments": None}
    fake_sess = ScoringSession(source_mp4=str(mp4), source_hash="h",
                                global_style="末日", frame_rate=24.0,
                                segments=[SegmentScore(0, 0.0, 2.0)])

    def fake_prepare_session(mp4_arg, style, work_dir, **kwargs):
        captured["dialogue_segments"] = kwargs.get("dialogue_segments")
        return fake_sess

    import sound_track_agent.facade as fac
    monkeypatch.setattr(fac, "load_session", lambda wd: None)
    monkeypatch.setattr(fac, "prepare_session", fake_prepare_session)
    monkeypatch.setattr(fac, "advance",
                        lambda sess, wd, **kw: sess)

    task = {"id": "t1", "name": "测试", "mp4": str(mp4), "style": "末日",
            "workflow_id": "wf", "output_dir": ""}
    editor = SoundtrackEditor(task, cfg, tmp_path)
    editor._run_pipeline("refine_segments")
    # 等待异步 worker 线程完成
    if editor._worker is not None:
        editor._worker.wait(5000)

    assert captured["dialogue_segments"] is not None
    assert len(captured["dialogue_segments"]) == 1
    assert captured["dialogue_segments"][0] == DialogueSegment(
        audio_path="/x/d.flac", t_start=0.0, duration=1.0)


def test_editor_no_dialogue_segments_when_no_match(tmp_path, monkeypatch):
    """cfg.video_tasks 无匹配时不应传 dialogue_segments（=None，走 Demucs 回退）。"""
    _app()
    from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor
    from sound_track_agent.session import ScoringSession, SegmentScore

    mp4 = tmp_path / "ep.mp4"; mp4.write_bytes(b"x")
    cfg = _cfg(tmp_path)
    cfg.video_tasks = [{"last_result": "/x/other.mp4", "timeline": {}}]

    captured = {"dialogue_segments": "<unset>"}
    fake_sess = ScoringSession(source_mp4=str(mp4), source_hash="h",
                                global_style="末日", frame_rate=24.0,
                                segments=[SegmentScore(0, 0.0, 2.0)])

    def fake_prepare_session(mp4_arg, style, work_dir, **kwargs):
        captured["dialogue_segments"] = kwargs.get("dialogue_segments", "<unset>")
        return fake_sess

    import sound_track_agent.facade as fac
    monkeypatch.setattr(fac, "load_session", lambda wd: None)
    monkeypatch.setattr(fac, "prepare_session", fake_prepare_session)
    monkeypatch.setattr(fac, "advance",
                        lambda sess, wd, **kw: sess)

    task = {"id": "t1", "name": "测试", "mp4": str(mp4), "style": "末日",
            "workflow_id": "wf", "output_dir": ""}
    editor = SoundtrackEditor(task, cfg, tmp_path)
    editor._run_pipeline("refine_segments")
    # 等待异步 worker 线程完成
    if editor._worker is not None:
        editor._worker.wait(5000)
    assert captured["dialogue_segments"] is None


def test_resegment_button_resets_flag_and_runs_refine(tmp_path, monkeypatch):
    """重排按钮：有候选 → 弹确认 + 清空候选 + segments_refined=False + 跑 refine。"""
    _app()
    from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor
    from sound_track_agent.session import (
        ScoringSession, SegmentScore, BGMCandidate, EmotionTag,
    )
    from PySide6.QtWidgets import QMessageBox

    mp4 = tmp_path / "ep.mp4"; mp4.write_bytes(b"x")
    cfg = _cfg(tmp_path)
    task = {"id": "t1", "name": "测试", "mp4": str(mp4), "style": "末日",
            "workflow_id": "wf", "output_dir": ""}
    editor = SoundtrackEditor(task, cfg, tmp_path)

    seg = SegmentScore(0, 0.0, 2.0)
    seg.status = "generated"
    seg.candidates = [BGMCandidate(path="/b.mp3", seed=1, prompt="t")]
    seg.chosen_candidate = 0
    seg.music_prompt = "x"
    seg.emotion = EmotionTag()
    sess = ScoringSession(source_mp4=str(mp4), source_hash="h",
                          global_style="末日", frame_rate=24.0,
                          segments=[seg])
    sess.segments_refined = True
    editor._session = sess

    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: QMessageBox.Yes)
    captured = {"stop_after": None}
    monkeypatch.setattr(editor, "_run_pipeline",
                        lambda stop_after: captured.__setitem__("stop_after", stop_after))

    editor._on_resegment()

    assert sess.segments_refined is False
    assert sess.segments[0].candidates == []
    assert sess.segments[0].chosen_candidate is None
    assert sess.segments[0].music_prompt == ""
    assert sess.segments[0].emotion is None
    assert sess.segments[0].status == "pending"
    assert captured["stop_after"] == "refine_segments"


def test_resegment_button_warns_when_no_session(tmp_path):
    """没 session 时点重排按钮 → 提示，不抛。"""
    _app()
    from unittest.mock import patch
    from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor
    from PySide6.QtWidgets import QMessageBox

    cfg = _cfg(tmp_path)
    task = {"id": "t1", "name": "测试", "mp4": str(tmp_path / "ep.mp4"),
            "style": "末日", "workflow_id": "wf", "output_dir": ""}
    editor = SoundtrackEditor(task, cfg, tmp_path)
    editor._session = None

    with patch.object(QMessageBox, "warning") as warn:
        editor._on_resegment()
        warn.assert_called_once()


def test_resegment_button_blocks_when_worker_busy(tmp_path, monkeypatch):
    """worker 忙时点重排：弹 info 提示，**不得**清空候选或落盘。"""
    _app()
    from unittest.mock import patch
    from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor
    from sound_track_agent.session import (
        ScoringSession, SegmentScore, BGMCandidate,
    )
    from PySide6.QtWidgets import QMessageBox

    mp4 = tmp_path / "ep.mp4"; mp4.write_bytes(b"x")
    cfg = _cfg(tmp_path)
    task = {"id": "t1", "name": "测试", "mp4": str(mp4),
            "style": "末日", "workflow_id": "wf", "output_dir": ""}
    editor = SoundtrackEditor(task, cfg, tmp_path)

    seg = SegmentScore(0, 0.0, 2.0)
    seg.candidates = [BGMCandidate(path="/b.mp3", seed=1, prompt="t")]
    sess = ScoringSession(source_mp4=str(mp4), source_hash="h",
                          global_style="末日", frame_rate=24.0,
                          segments=[seg])
    sess.segments_refined = True
    editor._session = sess

    monkeypatch.setattr(editor, "_worker_busy", lambda: True)
    persisted = {"called": False}
    monkeypatch.setattr(editor, "_persist_session",
                        lambda: persisted.__setitem__("called", True))

    with patch.object(QMessageBox, "information") as info:
        editor._on_resegment()
        info.assert_called_once()
    # 候选未被清空，flag 未翻转，未落盘
    assert sess.segments[0].candidates != []
    assert sess.segments_refined is True
    assert persisted["called"] is False
