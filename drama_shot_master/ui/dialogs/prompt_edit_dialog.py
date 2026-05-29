"""BGM/SFX prompt 编辑弹窗。双击 cue 触发；OK 后由调用方 build ChangePrompt 命令。"""
from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QPlainTextEdit, QDialogButtonBox, QLabel,
)


class PromptEditDialog(QDialog):
    def __init__(self, initial_prompt: str, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(500)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Prompt（短描述/风格）:"))
        self.prompt_edit = QPlainTextEdit(initial_prompt or "")
        self.prompt_edit.setMinimumHeight(120)
        lay.addWidget(self.prompt_edit)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def to_payload(self) -> str:
        return self.prompt_edit.toPlainText().strip()
