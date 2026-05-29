import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter.ideate_page import IdeatePage


def _app():
    return QApplication.instance() or QApplication([])


class _StubClient:
    def __init__(self):
        self.select_calls = []
    def ideate_select(self, project_dir, selected_id):
        self.select_calls.append((Path(project_dir), selected_id))
        return {"saved": str(Path(project_dir) / "idea.json"),
                "selected": {"id": selected_id}}


def test_set_project_none_shows_placeholder():
    _app()
    p = IdeatePage(_StubClient())
    p.set_project(None)
    # 占位状态：send button 禁用
    assert p._send_btn.isEnabled() is False


def test_loads_idea_json_renders_candidates(tmp_path):
    _app()
    (tmp_path / "idea.json").write_text(json.dumps({
        "input": {}, "messages": [
            {"role": "user", "content": "出 2 个候选"},
            {"role": "assistant", "content": "候选 1..."},
        ],
        "candidates": [
            {"id": "c1", "title": "躺平农夫"},
            {"id": "c2", "title": "仙界 BUG"},
        ],
        "selected_id": "",
    }), encoding="utf-8")
    p = IdeatePage(_StubClient())
    p.set_project(tmp_path)
    # 2 张候选卡片渲染
    assert len(p._candidate_cards) == 2
    assert p._candidate_cards[0].candidate_id() == "c1"
    # 2 条消息气泡
    assert len(p._message_bubbles) == 2


def test_click_card_marks_local_only_not_calls_client(tmp_path):
    _app()
    (tmp_path / "idea.json").write_text(json.dumps({
        "input": {}, "messages": [],
        "candidates": [{"id": "c1", "title": "t1"},
                       {"id": "c2", "title": "t2"}],
        "selected_id": "",
    }), encoding="utf-8")
    client = _StubClient()
    p = IdeatePage(client)
    p.set_project(tmp_path)
    p._on_card_clicked("c2")
    assert p._selected_id == "c2"
    assert client.select_calls == []   # 不立即调
    # 按钮文本变
    assert "c2" in p._select_btn.text() or "推进" in p._select_btn.text()


def test_select_button_persists_and_emits_advance(tmp_path):
    _app()
    (tmp_path / "idea.json").write_text(json.dumps({
        "input": {}, "messages": [],
        "candidates": [{"id": "c1", "title": "t1"}],
        "selected_id": "",
    }), encoding="utf-8")
    client = _StubClient()
    p = IdeatePage(client)
    p.set_project(tmp_path)
    p._on_card_clicked("c1")
    emitted = []
    p.stageAdvanceRequested.connect(emitted.append)
    p._on_select_clicked()
    assert client.select_calls == [(tmp_path, "c1")]
    assert emitted == [1]    # 推进到第 1 个阶段（剧本）


def test_clear_chat_resets_messages_and_candidates(tmp_path, monkeypatch):
    _app()
    (tmp_path / "idea.json").write_text(json.dumps({
        "input": {}, "messages": [{"role": "user", "content": "x"}],
        "candidates": [{"id": "c1", "title": "t1"}],
        "selected_id": "c1",
    }), encoding="utf-8")
    p = IdeatePage(_StubClient())
    p.set_project(tmp_path)
    # monkeypatch confirm dialog → 自动 Yes
    import drama_shot_master.ui.widgets.screenwriter.ideate_page as m
    monkeypatch.setattr(m.QMessageBox, "question",
                         staticmethod(lambda *a, **kw: m.QMessageBox.Yes))
    p._on_clear_chat_clicked()
    assert p._messages == []
    assert p._candidates == []
    assert p._selected_id == ""


def test_two_projects_workers_kept_concurrently(tmp_path):
    _app()
    p = IdeatePage(_StubClient())
    pA = tmp_path / "A"; pA.mkdir()
    pB = tmp_path / "B"; pB.mkdir()
    # 模拟两个 worker（不 start，只挂在 dict 上）
    class _FakeWorker:
        def isRunning(self): return True
    p._workers[pA] = _FakeWorker()
    p._workers[pB] = _FakeWorker()
    p.set_project(pA)
    assert p.is_streaming(pA) is True
    assert p.is_streaming(pB) is True   # 切换不杀 B


def test_sse_event_for_inactive_project_emits_state_change(tmp_path):
    _app()
    p = IdeatePage(_StubClient())
    pA = tmp_path / "A"; pA.mkdir()
    pB = tmp_path / "B"; pB.mkdir()
    p.set_project(pA)
    flips = []
    p.projectStateChanged.connect(lambda: flips.append(True))
    # B 项目的 done 事件应触发 state change（让 TaskManager 刷新行）
    p._on_sse_event("done", {"result": {}, "saved": ""}, str(pB))
    assert len(flips) >= 1
