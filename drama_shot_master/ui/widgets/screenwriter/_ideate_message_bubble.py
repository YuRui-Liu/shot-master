"""单条聊天气泡：role 标签 + content。流式时 append_text 追加。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class _MessageBubble(QFrame):
    """User/Assistant 消息气泡。"""

    def __init__(self, role: str, content: str = "", parent=None):
        super().__init__(parent)
        self._role = role
        self.setObjectName("msgBubble" + role.capitalize())
        self.setFrameShape(QFrame.StyledPanel)
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 4, 6, 4); v.setSpacing(2)
        role_label = "你" if role == "user" else ("AI" if role == "assistant" else role)
        head = QLabel(f"<span style='color:#9aa0a6; font-size:9pt'>{role_label}</span>")
        head.setTextFormat(Qt.RichText)
        v.addWidget(head)
        self._body = QLabel(content)
        self._body.setWordWrap(True)
        self._body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(self._body)

    def append_text(self, chunk: str) -> None:
        """流式 delta 追加内容。"""
        self._body.setText(self._body.text() + chunk)

    def mark_aborted(self) -> None:
        self._body.setText(self._body.text() +
                            "  <span style='color:#9aa0a6'>(已中止)</span>")
        self._body.setTextFormat(Qt.RichText)
