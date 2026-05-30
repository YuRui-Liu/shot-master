"""AIChatPanel：对话式配乐方向面板（右栏上半常驻）。

会话区 + 当前方向块 + 输入框 + 双按钮。不直接调 LLM/生成——只发
directiveRequested(instruction, apply_prompts) 信号，由编辑器接线处理。
"""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QPlainTextEdit,
    QPushButton, QFrame,
)


class AIChatPanel(QWidget):
    directiveRequested = Signal(str, bool)   # (instruction, apply_prompts)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        title = QLabel("🤖 AI 配乐")
        title.setStyleSheet("font-weight:600;color:#4a83f0;")
        root.addWidget(title)

        self._chat_area = QScrollArea()
        self._chat_area.setWidgetResizable(True)
        self._chat_host = QWidget()
        self._chat_lay = QVBoxLayout(self._chat_host)
        self._chat_lay.setContentsMargins(2, 2, 2, 2)
        self._chat_lay.setSpacing(5)
        self._chat_lay.addStretch(1)
        self._chat_area.setWidget(self._chat_host)
        root.addWidget(self._chat_area, 1)

        dir_box = QFrame()
        dir_box.setStyleSheet("background:#1a1a2a;border-radius:4px;")
        dl = QVBoxLayout(dir_box)
        dl.setContentsMargins(6, 4, 6, 4)
        dl.addWidget(QLabel("📋 当前配乐方向"))
        self._dir_label = QLabel("（空，发指令开始）")
        self._dir_label.setWordWrap(True)
        self._dir_label.setStyleSheet("color:#cdd6f4;")
        dl.addWidget(self._dir_label)
        root.addWidget(dir_box)

        self._input = QPlainTextEdit()
        self._input.setPlaceholderText("用自然语言描述/修改配乐…")
        self._input.setMaximumHeight(60)
        root.addWidget(self._input)

        btns = QHBoxLayout()
        self.btn_update_only = QPushButton("仅更新方向")
        self.btn_update_only.clicked.connect(lambda: self._emit(False))
        self.btn_update_apply = QPushButton("更新并写入 prompt")
        self.btn_update_apply.setObjectName("AccentButton")
        self.btn_update_apply.clicked.connect(lambda: self._emit(True))
        btns.addWidget(self.btn_update_only)
        btns.addWidget(self.btn_update_apply)
        root.addLayout(btns)

        self._status = QLabel("")
        self._status.setStyleSheet("color:#a6adc8;font-size:11px;")
        root.addWidget(self._status)

    def _emit(self, apply_prompts: bool):
        text = self._input.toPlainText().strip()
        if not text:
            return
        self.directiveRequested.emit(text, apply_prompts)

    def set_directive(self, directive):
        while self._chat_lay.count() > 1:      # 保留末尾 stretch
            item = self._chat_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for m in (getattr(directive, "conversation", None) or []):
            self._add_bubble(m.get("role", ""), m.get("text", ""))
        g = getattr(directive, "global_directive", "") or "（空，发指令开始）"
        self._dir_label.setText(g)

    def _add_bubble(self, role: str, text: str):
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        if role == "user":
            lbl.setStyleSheet(
                "background:#3b6fd4;color:#fff;border-radius:7px;padding:5px 8px;")
            lbl.setAlignment(Qt.AlignRight)
        else:
            lbl.setStyleSheet(
                "background:#313145;color:#cdd6f4;border-radius:7px;padding:5px 8px;")
        self._chat_lay.insertWidget(self._chat_lay.count() - 1, lbl)

    def set_busy(self, on: bool):
        self.btn_update_only.setEnabled(not on)
        self.btn_update_apply.setEnabled(not on)
        self._input.setEnabled(not on)
        self._status.setText("AI 思考中…" if on else "")

    def append_error(self, msg: str):
        self._status.setText(msg)

    def _bubble_count(self) -> int:
        return self._chat_lay.count() - 1

    def _direction_text(self) -> str:
        return self._dir_label.text()
