"""IdeatePage：创意阶段子面板。

左 _CandidatesPanel + 右 _ChatPanel；首次对话前显 ContextForm，发完隐藏。
候选卡片本地点选 → 按钮[选定·推进 →] → ideate_select + emit stageAdvanceRequested(1)。
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit,
    QScrollArea, QSplitter, QLineEdit, QSpinBox, QFormLayout, QMessageBox,
    QFrame,
)

from drama_shot_master.ui.widgets.screenwriter.base_stage_page import _BaseStagePage
from drama_shot_master.ui.widgets.screenwriter._ideate_candidate_card import _CandidateCard
from drama_shot_master.ui.widgets.screenwriter._ideate_message_bubble import _MessageBubble
from drama_shot_master.ui.widgets.screenwriter.stream_worker import StreamWorker


class IdeatePage(_BaseStagePage):

    def __init__(self, client, parent=None):
        super().__init__(client, parent)
        self._messages: list[dict] = []
        self._candidates: list[dict] = []
        self._selected_id: str = ""
        self._context: dict = {}
        self._candidate_cards: list[_CandidateCard] = []
        self._message_bubbles: list[_MessageBubble] = []
        self._current_assistant_bubble: _MessageBubble | None = None
        # Legacy single-worker ref kept for _stop_stream compatibility;
        # canonical store is self._workers[project_dir] (from _BaseStagePage).
        self._worker: StreamWorker | None = None
        self._state: str = "idle"
        # 最近一次 _start_stream 请求参数，用于失败后一键重试
        self._last_stream_args: tuple | None = None
        self._build_ui()
        self.set_project(None)

    def _build_ui(self):
        # 左 chat（主输入/对话）+ 右 candidates（生成结果）
        # 顺序对齐用户预期：候选放右侧
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_chat_panel())
        splitter.addWidget(self._build_candidates_panel())
        splitter.setStretchFactor(0, 1); splitter.setStretchFactor(1, 0)
        splitter.setSizes([500, 300])
        root.addWidget(splitter)

    def _build_candidates_panel(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(260)
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        self._candidates_label = QLabel("候选 (0)")
        v.addWidget(self._candidates_label)
        # 滚动卡片容器
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        inner = QWidget(); self._candidates_layout = QVBoxLayout(inner)
        self._candidates_layout.setContentsMargins(2, 2, 2, 2)
        self._candidates_layout.setSpacing(4)
        self._candidates_layout.addStretch(1)
        scroll.setWidget(inner)
        v.addWidget(scroll, 1)
        # 选定推进按钮
        self._select_btn = QPushButton("（先点一张候选）")
        self._select_btn.setEnabled(False)
        self._select_btn.clicked.connect(self._on_select_clicked)
        v.addWidget(self._select_btn)
        return w

    def _build_chat_panel(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        # 顶 [清空对话]
        top = QHBoxLayout()
        top.addStretch(1)
        self._clear_btn = QPushButton("清空对话")
        self._clear_btn.clicked.connect(self._on_clear_chat_clicked)
        top.addWidget(self._clear_btn)
        v.addLayout(top)
        # 上次失败 banner（默认隐藏；失败时 set_text + 显示 [重试] 按钮）
        self._retry_banner = QFrame()
        self._retry_banner.setFrameShape(QFrame.StyledPanel)
        self._retry_banner.setStyleSheet(
            "QFrame { background:#3a2828; border:1px solid #5a3a3a; }"
            "QLabel { color:#ffb3b3; padding:4px; }")
        rb = QHBoxLayout(self._retry_banner)
        rb.setContentsMargins(6, 2, 6, 2)
        self._retry_msg = QLabel("")
        self._retry_msg.setWordWrap(True)
        rb.addWidget(self._retry_msg, 1)
        self._retry_btn = QPushButton("重试")
        self._retry_btn.clicked.connect(self._on_retry_clicked)
        rb.addWidget(self._retry_btn)
        self._retry_banner.hide()
        v.addWidget(self._retry_banner)
        # 首轮 context form
        self._context_form = self._build_context_form()
        v.addWidget(self._context_form)
        # 聊天历史滚动
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        inner = QWidget(); self._messages_layout = QVBoxLayout(inner)
        self._messages_layout.setContentsMargins(2, 2, 2, 2)
        self._messages_layout.setSpacing(4)
        self._messages_layout.addStretch(1)
        scroll.setWidget(inner)
        self._messages_scroll = scroll
        v.addWidget(scroll, 1)
        # 流式状态提示标签（streaming 时显示；醒目蓝色 + 字号）
        self._stream_label = QLabel("")
        self._stream_label.setStyleSheet(
            "color:#4a9eff; font-weight:bold; padding:4px;"
            " background:#1a2a3a; border-radius:3px;")
        self._stream_label.hide()
        v.addWidget(self._stream_label)
        # 输入行
        input_row = QHBoxLayout()
        self._input = QPlainTextEdit(); self._input.setMaximumHeight(80)
        self._input.setPlaceholderText("输入追问…（已生成候选后用）")
        self._send_btn = QPushButton("发送")
        self._send_btn.clicked.connect(self._on_send_clicked)
        input_row.addWidget(self._input, 1)
        input_row.addWidget(self._send_btn)
        v.addLayout(input_row)
        return w

    def _build_context_form(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.StyledPanel)
        form = QFormLayout(f)
        form.setContentsMargins(6, 6, 6, 6)
        self._ctx_core_idea = QLineEdit()
        self._ctx_core_idea.setPlaceholderText("一句话主旨，如：守株待兔")
        self._ctx_genre = QLineEdit()
        self._ctx_genre.setPlaceholderText("题材标签，逗号分隔：古风, 寓言")
        self._ctx_duration = QSpinBox(); self._ctx_duration.setRange(15, 600)
        self._ctx_duration.setValue(60)
        self._ctx_visual = QLineEdit()
        self._ctx_visual.setPlaceholderText("视觉风格，如：水墨")
        self._ctx_extra = QLineEdit()
        self._ctx_extra.setPlaceholderText("额外约束（可空）")
        form.addRow("主旨", self._ctx_core_idea)
        form.addRow("题材", self._ctx_genre)
        form.addRow("时长(s)", self._ctx_duration)
        form.addRow("视觉风格", self._ctx_visual)
        form.addRow("额外约束", self._ctx_extra)
        self._gen_first_btn = QPushButton("生成 3 个候选")
        self._gen_first_btn.clicked.connect(self._on_first_gen_clicked)
        form.addRow("", self._gen_first_btn)
        return f

    # —— 流式 UI 状态 ——

    def _enter_streaming_view(self):
        """进入 streaming 显示状态：切换发送按钮为「中止」，显示流式提示。
        初始显示「正在连接 LLM…」，首个 delta 到达后切到「已 N 字」。"""
        # 进入流式：清掉上次失败 banner
        self._retry_banner.hide()
        self._stream_label.setText("● 正在连接 LLM…")
        self._stream_label.show()
        self._send_btn.setText("▣ 中止")
        try:
            self._send_btn.clicked.disconnect()
        except RuntimeError:
            pass
        self._send_btn.clicked.connect(self._stop_stream)

    def _exit_streaming_view(self):
        """退出 streaming 显示状态：恢复发送按钮，隐藏流式提示。"""
        self._stream_label.hide()
        self._stream_label.setText("")
        self._reset_send_button()

    # —— set_project / try_release ————

    def set_project(self, path: Path | None):
        if self._project_dir is not None and not self.try_release():
            return
        old = self._project_dir
        self._project_dir = path
        # 状态重置
        self._messages = []
        self._candidates = []
        self._selected_id = ""
        self._context = {}
        self._render_candidates()
        self._render_messages()
        if path is None:
            self._context_form.hide()
            self._send_btn.setEnabled(False)
            self._gen_first_btn.setEnabled(False)
            self._exit_streaming_view()
            return
        self._send_btn.setEnabled(True)
        self._gen_first_btn.setEnabled(True)
        idea_path = path / "idea.json"
        if idea_path.is_file():
            try:
                idea = json.loads(idea_path.read_text(encoding="utf-8"))
                self._messages = list(idea.get("messages", []))
                self._candidates = list(idea.get("candidates", []))
                self._selected_id = idea.get("selected_id", "")
                self._context = dict(idea.get("input", {}))
            except Exception:
                pass
        self._render_candidates()
        self._render_messages()
        # context form 显示规则：从未对话过才显
        self._context_form.setVisible(not self._messages)
        # 如果该项目有 active worker → UI 接管显示
        if path in self._workers and self._workers[path] and self._workers[path].isRunning():
            self._enter_streaming_view()
            n = len(self._buf_by_project.get(path, ""))
            self._stream_label.setText(f"● 流式 · 已 {n} 字（后台跑）")
        else:
            self._exit_streaming_view()
        self._on_project_switched(old=old, new=path)

    def try_release(self) -> bool:
        # 创意阶段无 dirty 概念（每条 user 发都立刻产 idea.json）；总返 True
        return True

    # —— 渲染 ——

    def _render_candidates(self):
        # 清空旧卡
        for c in self._candidate_cards:
            c.deleteLater()
        self._candidate_cards = []
        # 加新卡（在 stretch 之前插）
        for cand in self._candidates:
            card = _CandidateCard(cand)
            card.clicked.connect(self._on_card_clicked)
            card.set_selected(cand.get("id") == self._selected_id)
            self._candidates_layout.insertWidget(
                self._candidates_layout.count() - 1, card)
            self._candidate_cards.append(card)
        self._candidates_label.setText(f"候选 ({len(self._candidates)})")
        # 按钮文本与可用性
        if self._selected_id:
            self._select_btn.setText(f"选定 {self._selected_id} · 推进 →")
            self._select_btn.setEnabled(True)
        else:
            self._select_btn.setText("（先点一张候选）")
            self._select_btn.setEnabled(False)

    def _render_messages(self):
        for b in self._message_bubbles:
            b.deleteLater()
        self._message_bubbles = []
        for m in self._messages:
            bub = _MessageBubble(m.get("role", "user"), m.get("content", ""))
            self._messages_layout.insertWidget(
                self._messages_layout.count() - 1, bub)
            self._message_bubbles.append(bub)
        self._current_assistant_bubble = None

    # —— 用户交互 ——

    def _collect_context(self) -> dict:
        return {
            "core_idea": self._ctx_core_idea.text().strip(),
            "genre_tags": [t.strip() for t in
                           self._ctx_genre.text().split(",") if t.strip()],
            "format": "短剧",
            "tone_tags": [],
            "visual_style": self._ctx_visual.text().strip(),
            "candidate_count": 3,
            "duration_sec": int(self._ctx_duration.value()),
            "extra_constraints": self._ctx_extra.text().strip(),
        }

    def _on_first_gen_clicked(self):
        if self._project_dir is None:
            return
        self._context = self._collect_context()
        self._context_form.hide()
        self._send_user_text("生成候选（按上面 context）")

    def _on_send_clicked(self):
        text = self._input.toPlainText().strip()
        if not text or self._project_dir is None:
            return
        self._input.clear()
        self._send_user_text(text)

    def _send_user_text(self, text: str):
        # 追加 user message
        self._messages.append({"role": "user", "content": text})
        ub = _MessageBubble("user", text)
        self._messages_layout.insertWidget(
            self._messages_layout.count() - 1, ub)
        self._message_bubbles.append(ub)
        # 起 assistant 流
        self._current_assistant_bubble = _MessageBubble("assistant", "")
        self._messages_layout.insertWidget(
            self._messages_layout.count() - 1, self._current_assistant_bubble)
        self._message_bubbles.append(self._current_assistant_bubble)

        body = {
            "project_dir": str(self._project_dir),
            "context": self._context,
            "messages": list(self._messages),
            "auto_save_idea_json": True,
        }
        self._start_stream("/ideate/chat", body)

    def _on_card_clicked(self, cid: str):
        self._selected_id = cid
        for c in self._candidate_cards:
            c.set_selected(c.candidate_id() == cid)
        self._select_btn.setText(f"选定 {cid} · 推进 →")
        self._select_btn.setEnabled(True)

    def _on_select_clicked(self):
        if not self._selected_id or self._project_dir is None:
            return
        try:
            self._client.ideate_select(self._project_dir, self._selected_id)
        except Exception as e:
            QMessageBox.warning(self, "选定失败", str(e))
            return
        self.projectStateChanged.emit()
        self.stageAdvanceRequested.emit(1)

    def _on_clear_chat_clicked(self):
        if QMessageBox.question(
                self, "清空对话",
                "会清空对话历史和当前候选（不删除项目目录），继续？",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self._messages = []
        self._candidates = []
        self._selected_id = ""
        self._last_stream_args = None
        self._retry_banner.hide()
        self._render_candidates()
        self._render_messages()
        self._context_form.show()

    # —— SSE 流 ——

    def _start_stream(self, path, body, params=None):
        if self._project_dir is None:
            return
        # 缓存最近一次请求，用于失败时一键重试
        self._last_stream_args = (path, body, params)
        self._state_by_project[self._project_dir] = "streaming"
        # 重置 buffer 让字数计数从 0 开始（旧字数会污染 label）
        self._buf_by_project[self._project_dir] = ""
        self._enter_streaming_view()
        worker = StreamWorker(self._client, path, body, params,
                               project_dir=self._project_dir, parent=self)
        self._workers[self._project_dir] = worker
        # Keep legacy ref for _stop_stream (points to the current project's worker)
        self._worker = worker
        worker.event.connect(self._on_sse_event)
        worker.finished_ok.connect(self._on_stream_done_signal)
        worker.failed.connect(self._on_stream_failed)
        worker.start()

    def _stop_stream(self):
        w = self._active_worker()
        if w and w.isRunning():
            w.stop()
            w.wait(2000)
        if self._project_dir is not None:
            self._state_by_project[self._project_dir] = "idle"
            self._workers[self._project_dir] = None
        self._state = "idle"
        self._worker = None
        if self._current_assistant_bubble is not None:
            self._current_assistant_bubble.mark_aborted()
            self._current_assistant_bubble = None
        self._exit_streaming_view()

    def _on_sse_event(self, event_name: str, data: dict, project_dir_str: str):
        proj = Path(project_dir_str)
        # 累 buffer（不论是否当前显示）
        if event_name == "delta":
            text = data.get("text", "")
            self._buf_by_project[proj] = self._buf_by_project.get(proj, "") + text
        elif event_name == "done":
            self._state_by_project[proj] = "done"
            self._handle_done_for_project(proj, data)
        elif event_name == "error":
            self._error_by_project[proj] = data.get("hint") or data.get("message", "")
            self._state_by_project[proj] = "error"

        # 只有当前显示项目才动 UI
        if proj != self._project_dir:
            # 后台项目状态变了，通知 TaskManager 刷新行
            if event_name in ("done", "error"):
                self.projectStateChanged.emit()
            return

        # 当前显示项目的 UI 更新
        self._render_sse_for_current(event_name, data)

    def _handle_done_for_project(self, proj: Path, data: dict):
        """落盘逻辑：从 idea.json 重读（Agent 已在服务端落盘），解析候选。
        此方法不操作 UI，安全用于后台项目。"""
        # idea.json 由 Agent 服务端写出；本端只重读更新内存。
        # 当前项目的 UI 刷新由 _render_sse_for_current("done", ...) 负责。
        pass

    def _render_sse_for_current(self, event_name: str, data: dict):
        """UI 更新部分——仅在 proj == self._project_dir 时调用。"""
        if event_name == "delta":
            text = data.get("text", "")
            if text and self._current_assistant_bubble is not None:
                self._current_assistant_bubble.append_text(text)
            # 更新流式 label：从"正在连接"切到字数计数
            if self._project_dir is not None:
                n = len(self._buf_by_project.get(self._project_dir, ""))
                self._stream_label.setText(f"● 流式生成中… 已收 {n} 字")
            # 自动滚到底部，让用户看到新增内容
            sb = self._messages_scroll.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _on_stream_done_signal(self, project_dir_str: str):
        proj = Path(project_dir_str)
        # worker 完成清理
        if proj in self._workers:
            self._workers[proj] = None
        if proj == self._project_dir:
            self._worker = None
            self._state = "idle"
            self._exit_streaming_view()
            # 重读 idea.json（Agent 已落盘 + 解析候选）
            idea_path = proj / "idea.json"
            if idea_path.is_file():
                try:
                    idea = json.loads(idea_path.read_text(encoding="utf-8"))
                    self._messages = list(idea.get("messages", []))
                    self._candidates = list(idea.get("candidates", []))
                    # 保留本地 selected_id 优先（用户在流式期间点过的）
                    if not self._selected_id:
                        self._selected_id = idea.get("selected_id", "")
                    self._render_candidates()
                    self._render_messages()
                except Exception:
                    pass
        self.projectStateChanged.emit()

    def _on_stream_failed(self, msg: str, project_dir_str: str):
        proj = Path(project_dir_str)
        self._error_by_project[proj] = msg
        self._state_by_project[proj] = "error"
        if proj in self._workers:
            self._workers[proj] = None
        if proj == self._project_dir:
            self._worker = None
            self._state = "idle"
            # 清掉空的 AI 气泡（连接立挂时还没收到任何 delta）；保留有内容的
            if self._current_assistant_bubble is not None:
                bubble = self._current_assistant_bubble
                self._current_assistant_bubble = None
                # 若 bubble._body 没文本，删除整条；否则只追加 (已中止)
                body_text = bubble._body.text().strip() if hasattr(bubble, "_body") else ""
                if not body_text:
                    self._messages_layout.removeWidget(bubble)
                    bubble.deleteLater()
                    if bubble in self._message_bubbles:
                        self._message_bubbles.remove(bubble)
                else:
                    bubble.mark_aborted()
            self._exit_streaming_view()
            # 失败 banner：上面顶 [重试] 按钮，不再弹 QMessageBox 阻塞
            short = msg if len(msg) < 200 else msg[:200] + "…"
            self._retry_msg.setText(f"⚠ 上次生成失败：{short}")
            self._retry_btn.setEnabled(self._last_stream_args is not None)
            self._retry_banner.show()
        self.projectStateChanged.emit()

    def _on_retry_clicked(self):
        """点击 [重试]：用最近一次 _start_stream 的参数重发。"""
        if self._last_stream_args is None or self._project_dir is None:
            return
        # 重新加一条 AI 气泡承接流（user 那条已在原位）
        self._current_assistant_bubble = _MessageBubble("assistant", "")
        self._messages_layout.insertWidget(
            self._messages_layout.count() - 1, self._current_assistant_bubble)
        self._message_bubbles.append(self._current_assistant_bubble)
        path, body, params = self._last_stream_args
        self._start_stream(path, body, params)

    def _reset_send_button(self):
        self._send_btn.setText("发送")
        try:
            self._send_btn.clicked.disconnect()
        except RuntimeError:
            pass
        self._send_btn.clicked.connect(self._on_send_clicked)
