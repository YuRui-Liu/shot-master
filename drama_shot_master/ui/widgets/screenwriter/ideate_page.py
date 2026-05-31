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
    QFrame, QToolButton,
)

from drama_shot_master.ui.widgets.screenwriter.base_stage_page import _BaseStagePage
from drama_shot_master.ui.widgets.screenwriter._ideate_candidate_card import _CandidateCard
from drama_shot_master.ui.widgets.screenwriter._ideate_message_bubble import _MessageBubble
from drama_shot_master.ui.widgets.screenwriter._paths import idea_file_in
from drama_shot_master.ui.widgets.screenwriter.stream_worker import StreamWorker
from drama_shot_master.ui.widgets.aspect_ratio_selector import (
    AspectRatioSelector, DEFAULT_RATIO,
)
from drama_shot_master.ui.dialogs.genre_picker_dialog import GenrePickerDialog
from drama_shot_master.ui.dialogs.style_bible_dialog import StyleBibleDialog
from drama_shot_master.core.compass.manifest import load_manifest, save_manifest
from drama_shot_master.core import genre_templates as _genres
from drama_shot_master.core import gen_context as _gc


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

        # —— 创意 ——
        self._ctx_core_idea = QLineEdit()
        self._ctx_core_idea.setPlaceholderText("一句话主旨，如：高山流水")
        form.addRow("主旨", self._ctx_core_idea)

        # —— 题材（结构化 chip + 选模板按钮）——
        genre_row = QHBoxLayout()
        self._genre_chip = QLabel("未选题材")
        self._genre_chip.setStyleSheet(
            "color:#cdbcff; background:#241c3a; border:1px solid #4b2fb0;"
            " border-radius:10px; padding:3px 10px;")
        self._pick_genre_btn = QPushButton("选题材模板")
        self._pick_genre_btn.clicked.connect(self._on_pick_genre_clicked)
        genre_row.addWidget(self._genre_chip, 1)
        genre_row.addWidget(self._pick_genre_btn)
        form.addRow("题材", genre_row)

        # —— 风格圣经（chip + 选模板按钮）——
        style_row = QHBoxLayout()
        self._style_chip = QLabel("未选风格")
        self._style_chip.setStyleSheet(
            "color:#bcd6ff; background:#1f2030; border:1px solid #7c5cff;"
            " border-radius:10px; padding:3px 10px;")
        self._pick_style_btn = QPushButton("选风格圣经")
        self._pick_style_btn.clicked.connect(self._on_pick_style_clicked)
        style_row.addWidget(self._style_chip, 1)
        style_row.addWidget(self._pick_style_btn)
        form.addRow("风格圣经", style_row)

        # —— 画幅 ——
        self._aspect_selector = AspectRatioSelector()
        self._aspect_selector.changed.connect(self._on_aspect_changed)
        form.addRow("画幅", self._aspect_selector)

        # —— 规格：集数 / 时长 / 候选数 ——
        spec_row = QHBoxLayout()
        self._ctx_episodes = QSpinBox(); self._ctx_episodes.setRange(1, 999)
        self._ctx_episodes.setValue(1)
        self._ctx_duration = QSpinBox(); self._ctx_duration.setRange(15, 600)
        self._ctx_duration.setValue(60)
        self._ctx_cand_count = QSpinBox(); self._ctx_cand_count.setRange(1, 9)
        self._ctx_cand_count.setValue(3)
        spec_row.addWidget(QLabel("集数")); spec_row.addWidget(self._ctx_episodes)
        spec_row.addWidget(QLabel("时长(s)")); spec_row.addWidget(self._ctx_duration)
        spec_row.addWidget(QLabel("候选数")); spec_row.addWidget(self._ctx_cand_count)
        spec_row.addStretch(1)
        form.addRow("规格", spec_row)

        # —— 高级折叠（自由文本，兼容；默认收起）——
        self._adv_toggle = QToolButton()
        self._adv_toggle.setText("高级（自由文本，可选）")
        self._adv_toggle.setCheckable(True)
        self._adv_toggle.setChecked(False)
        self._adv_toggle.setStyleSheet("QToolButton { border:none; color:#9aa0a6; }")
        self._adv_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._adv_toggle.setArrowType(Qt.RightArrow)
        self._adv_toggle.toggled.connect(self._on_adv_toggled)
        form.addRow("", self._adv_toggle)

        self._adv_body = QWidget()
        adv_form = QFormLayout(self._adv_body)
        adv_form.setContentsMargins(0, 0, 0, 0)
        self._ctx_genre = QLineEdit()
        self._ctx_genre.setPlaceholderText("题材标签，逗号分隔：古风, 玄幻， 言情, 寓言等")
        self._ctx_visual = QLineEdit()
        self._ctx_visual.setPlaceholderText("视觉风格，如：水墨")
        self._ctx_extra = QLineEdit()
        self._ctx_extra.setPlaceholderText("额外约束（可空）")
        adv_form.addRow("题材标签", self._ctx_genre)
        adv_form.addRow("视觉风格", self._ctx_visual)
        adv_form.addRow("额外约束", self._ctx_extra)
        self._adv_body.setVisible(False)
        form.addRow("", self._adv_body)

        # —— 注入预览 ——
        self._injection_preview = QPlainTextEdit()
        self._injection_preview.setReadOnly(True)
        self._injection_preview.setMaximumHeight(120)
        self._injection_preview.setPlaceholderText("（本次生成将注入的题材/风格/规格摘要）")
        self._injection_preview.setStyleSheet(
            "QPlainTextEdit { background:#161821; color:#9fb4d8;"
            " border:1px solid #2a3142; border-radius:4px; font-size:11px; }")
        form.addRow("本次注入", self._injection_preview)

        self._gen_first_btn = QPushButton("生成候选")
        self._gen_first_btn.clicked.connect(self._on_first_gen_clicked)
        form.addRow("", self._gen_first_btn)
        return f

    # —— 结构化（题材/风格/画幅/注入预览）——

    def _refresh_structured(self):
        """从 project.json 刷新题材/风格 chip、画幅初值、注入预览。
        无项目时仅置占位，不抛。"""
        if self._project_dir is None:
            self._genre_chip.setText("未选题材")
            self._style_chip.setText("未选风格")
            self._aspect_selector.set_value(DEFAULT_RATIO)
            self._injection_preview.setPlainText("")
            return
        m = load_manifest(self._project_dir)
        # 题材 chip
        self._genre_chip.setText(self._genre_display(m.params.get("genre")))
        # 风格 chip
        ref = (m.style_bible or {}).get("ref") if isinstance(m.style_bible, dict) else None
        self._style_chip.setText(str(ref) if ref else "未选风格")
        # 画幅初值：params.aspect_ratio 或 cfg.last_aspect_ratio 或默认
        aspect = (m.params or {}).get("aspect_ratio") \
            or self._cfg_get("last_aspect_ratio") or DEFAULT_RATIO
        self._aspect_selector.set_value(aspect)
        self._refresh_injection_preview(m)

    @staticmethod
    def _genre_id_of(raw) -> str:
        """params.genre 可为 {"genre":id,"sub":[]} 或裸字符串 → 取主题材 id。"""
        if isinstance(raw, dict):
            return str(raw.get("genre") or "")
        if isinstance(raw, str):
            return raw
        return ""

    def _genre_display(self, raw) -> str:
        gid = self._genre_id_of(raw)
        if not gid:
            return "未选题材"
        try:
            return _genres.load_genre(gid).get("display_name", gid)
        except Exception:
            return gid

    def _refresh_injection_preview(self, manifest=None):
        """读 manifest genre/style → gen_context 摘要 + 规格（画幅/集数/时长）。"""
        if self._project_dir is None:
            self._injection_preview.setPlainText("")
            return
        m = manifest if manifest is not None else load_manifest(self._project_dir)
        parts: list[str] = []
        # 题材摘要
        gid = self._genre_id_of((m.params or {}).get("genre"))
        if gid:
            try:
                gtxt = _gc.build_genre_context(_genres.load_genre(gid))
            except Exception:
                gtxt = ""
            if gtxt:
                parts.append("【题材注入】\n" + gtxt)
        # 风格摘要
        from drama_shot_master.core import style_bible as _styles
        ref = (m.style_bible or {}).get("ref") if isinstance(m.style_bible, dict) else None
        if ref:
            try:
                sd = _styles.get_style(str(ref))
                stxt = _gc.build_style_context(sd, stage="render") if sd else ""
            except Exception:
                stxt = ""
            if stxt:
                parts.append("【风格注入】" + stxt)
        # 规格行
        aspect = (m.params or {}).get("aspect_ratio") or self._aspect_selector.value()
        ep = (m.params or {}).get("episode_count")
        dur = (m.params or {}).get("duration_per_unit_sec")
        spec_bits = [f"画幅 {aspect}"]
        if ep:
            spec_bits.append(f"集数 {ep}")
        if dur:
            spec_bits.append(f"时长 {dur}s")
        parts.append("【规格】" + " · ".join(spec_bits))
        self._injection_preview.setPlainText("\n\n".join(parts))

    def _on_pick_genre_clicked(self):
        if self._project_dir is None:
            return
        dlg = GenrePickerDialog(self)
        if dlg.exec() and dlg.result_value():
            res = dlg.result_value()
            m = load_manifest(self._project_dir)
            # 存 dict 形态 {"genre":id,"sub":[...]}（与 client.assemble_gen_context 读法一致）
            m.params["genre"] = {
                "genre": res.get("genre") or "",
                "sub": list(res.get("sub") or []),
            }
            save_manifest(m, self._project_dir)
            self._refresh_structured()
            self.projectStateChanged.emit()

    def _on_pick_style_clicked(self):
        if self._project_dir is None:
            return
        dlg = StyleBibleDialog(parent=self)
        if dlg.exec() and dlg.result_value():
            res = dlg.result_value()
            m = load_manifest(self._project_dir)
            m.style_bible["ref"] = res.get("ref") or ""
            m.style_bible["category"] = res.get("category") or ""
            save_manifest(m, self._project_dir)
            self._refresh_structured()
            self.projectStateChanged.emit()

    def _on_aspect_changed(self, ratio: str):
        if self._project_dir is not None:
            m = load_manifest(self._project_dir)
            m.params["aspect_ratio"] = ratio
            save_manifest(m, self._project_dir)
            self._refresh_injection_preview()
        # 记住上次（cfg 可写则写，否则静默跳过）
        self._cfg_set("last_aspect_ratio", ratio)

    def _on_adv_toggled(self, on: bool):
        self._adv_toggle.setArrowType(Qt.DownArrow if on else Qt.RightArrow)
        self._adv_body.setVisible(on)

    # —— cfg 记忆（best-effort；client/无 cfg 时静默降级）——

    def _cfg(self):
        return getattr(self._client, "cfg", None) or getattr(self._client, "config", None)

    def _cfg_get(self, key: str):
        cfg = self._cfg()
        if cfg is None:
            return None
        return getattr(cfg, key, None)

    def _cfg_set(self, key: str, value):
        cfg = self._cfg()
        if cfg is None:
            return
        try:
            setattr(cfg, key, value)
            save = getattr(cfg, "save", None)
            if callable(save):
                save()
        except Exception:
            pass

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
            self._refresh_structured()
            self._context_form.hide()
            self._send_btn.setEnabled(False)
            self._gen_first_btn.setEnabled(False)
            self._exit_streaming_view()
            return
        self._send_btn.setEnabled(True)
        self._gen_first_btn.setEnabled(True)
        # 题材/风格 chip、画幅初值、注入预览 ← project.json
        self._refresh_structured()
        idea_path = idea_file_in(path)
        if idea_path is not None:
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
            "candidate_count": int(self._ctx_cand_count.value()),
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
            # 防御：流结束但没收到任何 delta（agent LLM 返回空 → idea.json
            # 不会被写或写出空 candidates）。当作错误，让 retry banner 提示
            buf = self._buf_by_project.get(proj, "")
            if not buf.strip():
                self._on_stream_failed(
                    "LLM 返回空响应。检查（按概率排序）：\n"
                    "1) [设置 → 编剧] 是否给『创意』阶段选了平台 + 模型名\n"
                    "   （比如 deepseek + deepseek-chat / deepseek-reasoner）\n"
                    "2) 模型名是否在所选平台真实存在（DeepSeek 列表：\n"
                    "   https://api-docs.deepseek.com/zh-cn/api/list-models）\n"
                    "3) 改完设置后需重启程序，agent 才能拿到新 env\n"
                    "4) 看 ~/.drama_shot_master/logs/screenwriter_agent.log 末尾",
                    project_dir_str)
                return
            # 重读创意.json（Agent 已落盘 + 解析候选；含旧名兼容）
            idea_path = idea_file_in(proj)
            if idea_path is not None:
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
