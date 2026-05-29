"""_EpisodeSelector：集选择 widget。

读 剧本.json.episodes 渲染 QComboBox（label 含状态点 ✓/○）+
signal episodeChanged(str)。可选 file_pattern_for_status 决定状态点
按哪个文件名 pattern 扫描（例如 '分镜_{ep}.json' 给 StoryboardPage 用）。
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QComboBox


class _EpisodeSelector(QWidget):
    episodeChanged = Signal(str)

    def __init__(self, parent=None, file_pattern_for_status: str | None = None):
        super().__init__(parent)
        self._project_dir: Path | None = None
        self._episodes: list[dict] = []
        self._pattern = file_pattern_for_status
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(QLabel("当前集:"))
        self.combo = QComboBox()
        self.combo.setMinimumWidth(160)
        self.combo.currentIndexChanged.connect(self._on_changed)
        h.addWidget(self.combo)
        h.addStretch(1)

    def set_project(self, project_dir: Path | None) -> None:
        self._project_dir = project_dir
        self.combo.blockSignals(True)
        self.combo.clear()
        self._episodes = []
        si = {}
        if project_dir is not None:
            si_path = project_dir / "剧本.json"
            if si_path.is_file():
                try:
                    si = json.loads(si_path.read_text(encoding="utf-8"))
                    self._episodes = list(si.get("episodes", []))
                except Exception:
                    pass
            for ep in self._episodes:
                self.combo.addItem(self._format_label(ep["id"], ep.get("title", "")))
            sel = si.get("selected_episode", "")
            if sel:
                self.select_episode(sel)
        self.combo.blockSignals(False)

    def _format_label(self, ep_id: str, title: str) -> str:
        dot = self._status_dot(ep_id)
        parts = [p for p in (dot, ep_id, title) if p]
        return " ".join(parts)

    def _status_dot(self, ep_id: str) -> str:
        if self._pattern is None or self._project_dir is None:
            return ""
        target = self._project_dir / self._pattern.replace("{ep}", ep_id)
        return "✓" if target.exists() else "○"

    def current_episode(self) -> str:
        idx = self.combo.currentIndex()
        if 0 <= idx < len(self._episodes):
            return self._episodes[idx]["id"]
        return ""

    def select_episode(self, ep_id: str) -> None:
        for i, ep in enumerate(self._episodes):
            if ep["id"] == ep_id:
                self.combo.setCurrentIndex(i)
                return

    def refresh_status(self) -> None:
        self.combo.blockSignals(True)
        for i, ep in enumerate(self._episodes):
            self.combo.setItemText(
                i, self._format_label(ep["id"], ep.get("title", "")))
        self.combo.blockSignals(False)

    def _on_changed(self):
        ep = self.current_episode()
        if ep:
            self.episodeChanged.emit(ep)
