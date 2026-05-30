"""候选试听 mixin：候选行加 ▶/⏸ 按钮，本地 Overlay 单轨播放。"""
from __future__ import annotations

from pathlib import Path
from PySide6.QtWidgets import QPushButton


class CandidateAuditionMixin:
    """需宿主在 __init__ 调 self._init_audition()，并在重建候选时调
    self._reset_audition()，每候选用 self._make_play_button(idx, path) 取按钮。"""

    def _init_audition(self):
        from drama_shot_master.ui.widgets.overlay_audio import OverlayMixer
        self._audition = OverlayMixer(self)
        self._play_buttons: list[QPushButton] = []
        self._playing_idx: int | None = None

    def _reset_audition(self):
        self._audition.stop()
        self._playing_idx = None
        self._play_buttons = []

    def _make_play_button(self, idx: int, path: str) -> QPushButton:
        btn = QPushButton("▶")
        btn.setMaximumWidth(28)
        exists = bool(path) and Path(str(path)).exists()
        btn.setEnabled(exists)
        if not exists:
            btn.setToolTip("候选文件缺失")
        btn.clicked.connect(lambda _=False, i=idx, p=path: self._on_audition(i, p))
        self._play_buttons.append(btn)
        return btn

    def _on_audition(self, idx: int, path: str):
        if self._playing_idx == idx:
            self._audition.pause()
            self._set_btn(idx, "▶")
            self._playing_idx = None
            return
        if self._playing_idx is not None:
            self._set_btn(self._playing_idx, "▶")
        self._audition.set_track("audition", path)
        self._audition.set_enabled("audition", True)
        self._audition.seek(0.0)
        self._audition.play()
        self._set_btn(idx, "⏸")
        self._playing_idx = idx

    def _set_btn(self, idx: int, text: str):
        if 0 <= idx < len(self._play_buttons):
            self._play_buttons[idx].setText(text)
