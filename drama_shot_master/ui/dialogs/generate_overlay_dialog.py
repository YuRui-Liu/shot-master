"""框选生成对话框 — 子项目 #3d。

时间轴 Shift 框选区间后弹出：BGM/SFX 二选一 + prompt 多行 + 只读时长，
点「生成」后由调用方异步起 worker。打开时异步调注入的 ``suggest_fn``
预填一句 LLM 建议（不阻塞 exec，失败/未配置则留空降级）。
``result_value()`` 返回 ``(kind, prompt)`` 或 None（取消）。
"""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QDialogButtonBox,
    QLabel, QRadioButton, QButtonGroup,
)


class GenerateOverlayDialog(QDialog):
    """框选生成对话框。返回 (kind, prompt) 或 None(取消)。"""

    def __init__(self, t_start, t_end, *, suggest_fn=None, parent=None):
        super().__init__(parent)
        self._suggest_fn = suggest_fn
        self._t_start = float(t_start)
        self._t_end = float(t_end)
        self._duration = max(0.0, self._t_end - self._t_start)
        self.setWindowTitle("框选生成")
        self.setMinimumWidth(500)

        lay = QVBoxLayout(self)

        # 类型：BGM / SFX 二选一
        kind_row = QHBoxLayout()
        kind_row.addWidget(QLabel("类型:"))
        self.bgm_btn = QRadioButton("BGM 背景乐")
        self.sfx_btn = QRadioButton("SFX 音效")
        self.bgm_btn.setChecked(True)
        self._kind_group = QButtonGroup(self)
        self._kind_group.addButton(self.bgm_btn)
        self._kind_group.addButton(self.sfx_btn)
        kind_row.addWidget(self.bgm_btn)
        kind_row.addWidget(self.sfx_btn)
        kind_row.addStretch(1)
        lay.addLayout(kind_row)

        # 只读时长（= 框选长度）
        self.duration_label = QLabel(self._format_duration())
        lay.addWidget(self.duration_label)

        # prompt 多行
        lay.addWidget(QLabel("Prompt（短描述/风格，可改 LLM 建议）:"))
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setMinimumHeight(120)
        lay.addWidget(self.prompt_edit)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("生成")
        btns.button(QDialogButtonBox.Cancel).setText("取消")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        # 打开后异步预填 LLM 建议，不阻塞 exec
        if self._suggest_fn is not None:
            QTimer.singleShot(0, self._run_suggest)

    def _format_duration(self) -> str:
        return f"时长: {self._duration:g}s（框选长度，自动）"

    def current_kind(self) -> str:
        return "sfx" if self.sfx_btn.isChecked() else "bgm"

    def _run_suggest(self) -> None:
        """调注入的 suggest_fn 预填 prompt；失败/空则留空降级。"""
        if self._suggest_fn is None:
            return
        try:
            text = self._suggest_fn(self.current_kind(), self._t_start, self._t_end)
        except Exception:
            return
        # 用户已手填则不覆盖
        if text and not self.prompt_edit.toPlainText().strip():
            self.prompt_edit.setPlainText(str(text).strip())

    def result_value(self):
        """接受→(kind, prompt)；取消→None。"""
        if self.result() != QDialog.Accepted:
            return None
        return (self.current_kind(), self.prompt_edit.toPlainText().strip())
