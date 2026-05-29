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


def test_failure_shows_retry_banner_and_caches_last_stream_args(tmp_path):
    """连接失败后：retry banner 显示，最近一次请求参数被缓存可一键重试。"""
    _app()
    p = IdeatePage(_StubClient())
    p.set_project(tmp_path)
    # 模拟 _start_stream 调用，缓存 args
    p._last_stream_args = ("/ideate/chat", {"project_dir": str(tmp_path)}, None)
    # 模拟当前 assistant bubble（_send_user_text 会建）
    from drama_shot_master.ui.widgets.screenwriter._ideate_message_bubble import _MessageBubble
    p._current_assistant_bubble = _MessageBubble("assistant", "")
    p._messages_layout.insertWidget(
        p._messages_layout.count() - 1, p._current_assistant_bubble)
    p._message_bubbles.append(p._current_assistant_bubble)
    # 触发失败
    p._on_stream_failed("connection refused", str(tmp_path))
    # banner 应可见、重试按钮启用、消息文本含错误
    assert not p._retry_banner.isHidden()
    assert p._retry_btn.isEnabled()
    assert "connection refused" in p._retry_msg.text()


def test_empty_assistant_bubble_removed_on_failure(tmp_path):
    """连接立挂、AI 气泡还没收到 delta 时，失败处理应删除空气泡（不留 '(已中止)' 噪音）。"""
    _app()
    p = IdeatePage(_StubClient())
    p.set_project(tmp_path)
    from drama_shot_master.ui.widgets.screenwriter._ideate_message_bubble import _MessageBubble
    empty_bubble = _MessageBubble("assistant", "")
    p._current_assistant_bubble = empty_bubble
    p._messages_layout.insertWidget(
        p._messages_layout.count() - 1, empty_bubble)
    p._message_bubbles.append(empty_bubble)
    n_before = len(p._message_bubbles)
    p._on_stream_failed("err", str(tmp_path))
    # 空气泡应被移除
    assert empty_bubble not in p._message_bubbles
    assert len(p._message_bubbles) == n_before - 1


def test_candidate_card_has_inline_stylesheet():
    """卡片应有自带 stylesheet（不能只靠 QFrame.StyledPanel）——
    否则在无主题 QSS 加载时完全没有可视差异。"""
    _app()
    from drama_shot_master.ui.widgets.screenwriter._ideate_candidate_card import _CandidateCard
    card = _CandidateCard({"id": "c1", "title": "测试候选"})
    ss = card.styleSheet()
    assert "background" in ss, "卡片应设 background 色，使其和聊天背景区分"
    assert "border" in ss, "卡片应设 border（含 selected 状态区分）"


def test_candidate_card_selected_visual_state_changes():
    _app()
    from drama_shot_master.ui.widgets.screenwriter._ideate_candidate_card import _CandidateCard
    card = _CandidateCard({"id": "c1", "title": "测试候选"})
    card.set_selected(False)
    assert card.property("selected") == "false"
    card.set_selected(True)
    assert card.property("selected") == "true"


def test_start_generation_if_idle_no_op_in_idle_no_upstream(tmp_path):
    """IdeatePage.start_generation_if_idle 应安全调，无副作用（IdeatePage
    创意阶段不是自动从上游 trigger 的）。"""
    _app()
    p = IdeatePage(_StubClient())
    p.set_project(tmp_path)
    # 不应抛
    p.start_generation_if_idle()
