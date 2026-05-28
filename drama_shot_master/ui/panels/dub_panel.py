"""配音编辑器：顶部单选 音色设计/声音克隆 + 对应表单 + 生成。内嵌于配音任务工作区。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QPlainTextEdit, QComboBox, QButtonGroup, QRadioButton, QStackedWidget,
    QLineEdit, QFileDialog, QDoubleSpinBox, QGroupBox, QMessageBox, QSizePolicy,
    QToolButton, QScrollArea, QGridLayout,
)

from drama_shot_master.config import Config
from drama_shot_master.core import tts_profiles as P
from drama_shot_master.providers import tts_builder as B
from drama_shot_master.providers import tts_submit
from drama_shot_master.ui.theme import _tokens, current_theme
from drama_shot_master.ui.worker import FunctionWorker


class _CollapsibleGroup(QWidget):
    """折叠分组：标题 QToolButton 切换内容显隐；set_buttons 建 4 列流式网格。"""

    def __init__(self, title: str, expanded: bool = False, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(2)
        self.head = QToolButton()
        self.head.setText(title)
        self.head.setCheckable(True)
        self.head.setChecked(expanded)
        self.head.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.head.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        _t = _tokens(current_theme(None))
        self.head.setStyleSheet(f"QToolButton{{border:none; font-weight:600; color:{_t['fg_muted']};}}")
        self.body = QWidget()
        self._grid = QGridLayout(self.body)
        self._grid.setContentsMargins(8, 2, 0, 6); self._grid.setSpacing(4)
        self.body.setVisible(expanded)
        v.addWidget(self.head); v.addWidget(self.body)
        self.head.toggled.connect(self._on_toggle)

    def _on_toggle(self, on: bool):
        self.head.setArrowType(Qt.DownArrow if on else Qt.RightArrow)
        self.body.setVisible(on)

    def set_buttons(self, widgets: list):
        for i, w in enumerate(widgets):
            self._grid.addWidget(w, i // 3, i % 3)   # 3 列(窄栏放得下 4 字标签)


class DubPanel(QWidget):
    statusChanged = Signal(str)            # 状态文字
    resultReady = Signal(str)              # FLAC 路径
    dirty = Signal()                       # 输入变化(用于持久化)

    def __init__(self, cfg: Config, payload: dict | None = None, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._worker = None
        self._build_ui()
        if payload:
            self.load_payload(payload)

    def _build_ui(self):
        _t = _tokens(current_theme(self.cfg))
        root = QVBoxLayout(self)
        # 顶部模式单选
        mode_row = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        self.rb_design = QRadioButton("音色设计")
        self.rb_clone = QRadioButton("声音克隆")
        self.rb_clone.setChecked(True)
        self.mode_group.addButton(self.rb_design, 0)
        self.mode_group.addButton(self.rb_clone, 1)
        mode_row.addWidget(self.rb_design)
        mode_row.addWidget(self.rb_clone)
        mode_row.addStretch(1)
        root.addLayout(mode_row)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_design_form())   # idx0
        self.stack.addWidget(self._build_clone_form())    # idx1
        self.stack.setCurrentIndex(1)
        self.mode_group.idClicked.connect(self.stack.setCurrentIndex)
        self.mode_group.idClicked.connect(lambda *_: self.dirty.emit())
        self._wire_dirty()

        cols = QHBoxLayout()
        cols.addWidget(self.stack, 3)                     # 左栏：输入
        cols.addWidget(self._build_palette(), 0)          # 右栏：快捷词
        root.addLayout(cols, 1)

        bar = QHBoxLayout()
        self.btn_gen = QPushButton("生成"); self.btn_gen.setObjectName("AccentButton")
        self.btn_gen.clicked.connect(self._generate)
        self.status_lbl = QLabel(""); self.status_lbl.setStyleSheet(f"color:{_t['fg_muted']}")
        # 状态文字不撑窗：忽略内容宽度+换行，长报错只进弹窗
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.btn_open = QPushButton("打开结果"); self.btn_open.setEnabled(False)
        self.btn_open.clicked.connect(self._open_result)
        self.btn_open_dir = QPushButton("打开输出文件夹")
        self.btn_open_dir.clicked.connect(self._open_output_dir)
        bar.addWidget(self.btn_gen); bar.addWidget(self.btn_open)
        bar.addWidget(self.btn_open_dir)
        bar.addWidget(self.status_lbl, 1)
        root.addLayout(bar)
        self._last_result = ""

    def _build_design_form(self):
        w = QWidget(); f = QFormLayout(w)
        self.d_text = QPlainTextEdit(); self.d_text.setFixedHeight(90)
        self.d_style = QPlainTextEdit(); self.d_style.setFixedHeight(70)
        # 显示中文标签，但实际取值(itemData)必须与工作流
        # TDQwen3TTSVoiceDesign(节点22) 的 language 枚举完全一致
        self.d_lang = QComboBox()
        for label, value in (
                ("自动", "Auto"), ("中文", "Chinese"), ("英语", "English"),
                ("日语", "Japanese"), ("韩语", "Korean"), ("德语", "German"),
                ("法语", "French"), ("俄语", "Russian"), ("葡萄牙语", "Portuguese"),
                ("西班牙语", "Spanish"), ("意大利语", "Italian")):
            self.d_lang.addItem(label, value)
        f.addRow("要生成文本", self.d_text)
        f.addRow("音色描述", self.d_style)
        f.addRow("语言", self.d_lang)
        return w

    def _build_clone_form(self):
        w = QWidget(); v = QVBoxLayout(w)
        f = QFormLayout()
        self.c_text = QPlainTextEdit(); self.c_text.setFixedHeight(80)
        self.c_speaker = QLineEdit(); self.c_speaker.setReadOnly(True)
        spk_btn = QPushButton("选参考音频")
        spk_btn.clicked.connect(lambda: self._pick_file(self.c_speaker))
        spk_row = QHBoxLayout(); spk_row.addWidget(self.c_speaker, 1); spk_row.addWidget(spk_btn)
        spk_wrap = QWidget(); spk_wrap.setLayout(spk_row)
        self.c_alpha = QDoubleSpinBox(); self.c_alpha.setRange(0.0, 2.0)
        self.c_alpha.setSingleStep(0.05); self.c_alpha.setValue(1.0)
        f.addRow("要生成文本", self.c_text)
        f.addRow("说话人参考音频", spk_wrap)
        f.addRow("情感强度", self.c_alpha)
        v.addLayout(f)

        # 4 选 1 情感子模式
        emo_box = QGroupBox("情感模式")
        ev = QVBoxLayout(emo_box)
        self.emo_group = QButtonGroup(self)
        labels = {1: "默认(随参考音频)", 2: "文本情绪", 3: "语音情绪模仿", 4: "情感向量"}
        for mid, txt in labels.items():
            rb = QRadioButton(txt)
            if mid == 1:
                rb.setChecked(True)
            self.emo_group.addButton(rb, mid)
            ev.addWidget(rb)
        v.addWidget(emo_box)

        self.emo_stack = QStackedWidget()
        # mode1 空
        self.emo_stack.addWidget(QWidget())
        # mode2 情感描述
        m2 = QWidget(); m2f = QFormLayout(m2)
        self.c_emo_text = QPlainTextEdit(); self.c_emo_text.setFixedHeight(60)
        m2f.addRow("情感描述", self.c_emo_text)
        self.emo_stack.addWidget(m2)
        # mode3 情感参考音频
        m3 = QWidget(); m3f = QFormLayout(m3)
        self.c_emo_audio = QLineEdit(); self.c_emo_audio.setReadOnly(True)
        ea_btn = QPushButton("选情感音频")
        ea_btn.clicked.connect(lambda: self._pick_file(self.c_emo_audio))
        ea_row = QHBoxLayout(); ea_row.addWidget(self.c_emo_audio, 1); ea_row.addWidget(ea_btn)
        ea_wrap = QWidget(); ea_wrap.setLayout(ea_row)
        m3f.addRow("情感参考音频", ea_wrap)
        self.emo_stack.addWidget(m3)
        # mode4 情感向量 8 维（IndexTTS2：0.0–1.4，各项之和建议 ≤1.5；>1.0 更夸张但可能影响音色相似度）
        m4 = QWidget(); m4f = QFormLayout(m4)
        hint = QLabel("点击右侧「情感语调」按钮可快速套用参考向量（YAML 可调）。0–1.4，sum≤1.5。")
        hint.setWordWrap(True); hint.setStyleSheet(f"color:{_t['fg_muted']}; font-size:9pt;")
        m4f.addRow(hint)
        self.c_vec = []
        for lbl in P.EMO_VECTOR_LABELS:
            sb = QDoubleSpinBox(); sb.setRange(0.0, 1.4); sb.setSingleStep(0.05)
            self.c_vec.append(sb)
            m4f.addRow(lbl, sb)
        self.emo_stack.addWidget(m4)
        v.addWidget(self.emo_stack)
        # emo 子模式 id(1..4) -> stack idx(0..3)
        self.emo_group.idClicked.connect(lambda mid: self.emo_stack.setCurrentIndex(mid - 1))
        self.emo_group.idClicked.connect(lambda *_: self.dirty.emit())
        return w

    def _build_palette(self) -> QWidget:
        from drama_shot_master.core.voice_presets import load_presets, load_emotion_vectors
        cats, note = load_presets()
        self._tone_vectors = load_emotion_vectors()   # {label: 8 维 list} 仅 情感语调 项有
        _t = _tokens(current_theme(self.cfg))
        wrap = QWidget(); wrap.setFixedWidth(360)
        outer = QVBoxLayout(wrap); outer.setContentsMargins(6, 0, 0, 0)
        outer.addWidget(QLabel("快捷音色提示词"))
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        inner = QWidget(); iv = QVBoxLayout(inner); iv.setContentsMargins(0, 0, 0, 0)
        note_lbl = QLabel(note); note_lbl.setWordWrap(True)
        note_lbl.setStyleSheet(f"color:{_t['fg_muted']}; font-size:9pt;")
        iv.addWidget(note_lbl)
        expand_default = {"方言", "情感语调"}
        for name, items in cats:
            grp = _CollapsibleGroup(name, expanded=(name in expand_default))
            btns = []
            for label, text in items:
                b = QPushButton(label)
                # label 透传给 _insert_preset：情感向量模式下按 label 查 vector
                b.clicked.connect(lambda _=False, t=text, lbl=label: self._insert_preset(t, lbl))
                btns.append(b)
            grp.set_buttons(btns)
            iv.addWidget(grp)
        iv.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)
        return wrap

    def _insert_preset(self, text: str, label: str = ""):
        """按钮点击分流：
        - 声音克隆 + emo_mode==4(情感向量) + 该 label 有 YAML vector → 写 8 个 spinbox
        - 其它情况（音色设计 / 克隆-默认/文本/语音情绪 / 无对应 vector）→ 插入提示词
        """
        vec = self._tone_vectors.get(label) if label else None
        if (vec is not None
                and self.current_mode() == "clone"
                and self.emo_group.checkedId() == 4):
            for sb, val in zip(self.c_vec, vec):
                sb.setValue(float(val))
            self.dirty.emit()
            return
        target = self.d_style if self.current_mode() == "design" else self.c_emo_text
        target.insertPlainText(text)

    def _open_output_dir(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        d = Path(self.cfg.dub_output_dir or ".") / "dub"
        d.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))

    def _wire_dirty(self):
        """所有输入变化都标脏 → 实时持久化（避免只在关窗时保存而丢内容）。"""
        d = self.dirty.emit
        for te in (self.d_text, self.d_style, self.c_text, self.c_emo_text):
            te.textChanged.connect(lambda *_: d())
        self.d_lang.currentIndexChanged.connect(lambda *_: d())
        self.c_alpha.valueChanged.connect(lambda *_: d())
        for sb in self.c_vec:
            sb.valueChanged.connect(lambda *_: d())

    def _pick_file(self, line: QLineEdit):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择音频", "", "音频 (*.wav *.flac *.mp3 *.m4a)")
        if p:
            line.setText(p); self.dirty.emit()

    # ---------- payload (持久化) ----------
    def current_mode(self) -> str:
        return "design" if self.rb_design.isChecked() else "clone"

    def to_payload(self) -> dict:
        if self.current_mode() == "design":
            return {"mode_kind": "design",
                    "text": self.d_text.toPlainText(),
                    "style": self.d_style.toPlainText(),
                    "language": self.d_lang.currentData()}
        return {"mode_kind": "clone",
                "text": self.c_text.toPlainText(),
                "speaker": self.c_speaker.text(),
                "alpha": self.c_alpha.value(),
                "emo_mode": self.emo_group.checkedId(),
                "emo_text": self.c_emo_text.toPlainText(),
                "emo_audio": self.c_emo_audio.text(),
                "emo_vector": [sb.value() for sb in self.c_vec]}

    def load_payload(self, p: dict):
        kind = p.get("mode_kind", "clone")
        if kind == "design":
            self.rb_design.setChecked(True); self.stack.setCurrentIndex(0)
            self.d_text.setPlainText(p.get("text", ""))
            self.d_style.setPlainText(p.get("style", ""))
            i = self.d_lang.findData(p.get("language", "Auto"))
            self.d_lang.setCurrentIndex(i if i >= 0 else 0)
        else:
            self.rb_clone.setChecked(True); self.stack.setCurrentIndex(1)
            self.c_text.setPlainText(p.get("text", ""))
            self.c_speaker.setText(p.get("speaker", ""))
            self.c_alpha.setValue(float(p.get("alpha", 1.0)))
            mid = int(p.get("emo_mode", 1) or 1)
            btn = self.emo_group.button(mid)
            if btn:
                btn.setChecked(True); self.emo_stack.setCurrentIndex(mid - 1)
            self.c_emo_text.setPlainText(p.get("emo_text", ""))
            self.c_emo_audio.setText(p.get("emo_audio", ""))
            for sb, val in zip(self.c_vec, p.get("emo_vector", []) or []):
                sb.setValue(float(val))

    # ---------- 生成 ----------
    def _profiles(self):
        ids = self.cfg.dub_workflow_ids
        nodes = self.cfg.dub_node_profiles or {}
        design = P.with_overrides(P.VOICE_DESIGN, ids.get("voice_design"),
                                  nodes.get("voice_design"))
        clone = P.with_overrides(P.VOICE_CLONE, ids.get("voice_clone"),
                                 nodes.get("voice_clone"))
        return design, clone

    def _generate(self):
        from drama_shot_master.licensing import manager
        if manager.requires_activation(manager.status().state):
            QMessageBox.warning(self, "需要激活", "授权无效或已过期，无法生成。")
            return
        design, clone = self._profiles()
        payload = self.to_payload()
        out_dir = Path(self.cfg.dub_output_dir or ".") / "dub"
        ts = __import__("time").strftime("%Y%m%d_%H%M%S")
        out_path = out_dir / f"dub_{ts}.flac"
        sampling = dict(self.cfg.dub_sampling or {})
        api_key = self.cfg.runninghub_api_key
        base_url = self.cfg.runninghub_base_url

        if payload["mode_kind"] == "design":
            if not payload["text"].strip():
                QMessageBox.information(self, "提示", "请填写要合成的文本"); return
            wf = design.workflow_id
            node_info = B.build_design_node_info(
                payload["text"], payload["style"], payload["language"], design)

            def task():
                from drama_shot_master.providers.runninghub import RunningHubClient
                with RunningHubClient(api_key, base_url=base_url) as client:
                    return tts_submit.submit_and_wait(
                        client, workflow_id=wf, node_info_list=node_info, out_path=out_path)
        else:
            if not payload["text"].strip() or not payload["speaker"]:
                QMessageBox.information(self, "提示", "请填写文本并选择说话人参考音频"); return
            mode = int(payload["emo_mode"])
            if mode == 3 and not payload["emo_audio"]:
                QMessageBox.information(self, "提示", "语音情绪模仿需选择情感参考音频"); return
            wf = clone.workflow_id
            spk = Path(payload["speaker"])
            emo_audio = Path(payload["emo_audio"]) if (mode == 3 and payload["emo_audio"]) else None

            def task():
                from drama_shot_master.providers.runninghub import RunningHubClient
                with RunningHubClient(api_key, base_url=base_url) as client:
                    uploads = [spk] + ([emo_audio] if emo_audio else [])
                    mp = tts_submit.upload_all(client, uploads)
                    node_info = B.build_clone_node_info(
                        text=payload["text"], mode=mode, emo_alpha=payload["alpha"],
                        speaker_file=mp[spk],
                        emo_text=payload["emo_text"],
                        emo_vector=payload["emo_vector"],
                        emo_audio_file=mp.get(emo_audio) if emo_audio else None,
                        sampling=sampling, prof=clone)
                    return tts_submit.submit_and_wait(
                        client, workflow_id=wf, node_info_list=node_info, out_path=out_path)

        self.btn_gen.setEnabled(False)
        self.status_lbl.setText("提交中…"); self.statusChanged.emit("RUNNING")
        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(self._on_done)
        self._worker.failed.connect(self._on_fail)
        self._worker.start()

    def _on_done(self, path):
        self._last_result = str(path)
        self.btn_gen.setEnabled(True); self.btn_open.setEnabled(True)
        self.status_lbl.setText(f"完成: {path}")
        self.statusChanged.emit("SUCCESS"); self.resultReady.emit(str(path))

    def _on_fail(self, err: str):
        self.btn_gen.setEnabled(True)
        self.status_lbl.setText("生成失败（详见弹窗）")
        self.statusChanged.emit("FAILED")
        QMessageBox.critical(self, "生成失败", err)

    def _open_result(self):
        if not self._last_result:
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._last_result))
