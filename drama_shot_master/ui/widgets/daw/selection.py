"""选区 + 多选 model。"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from PySide6.QtCore import QObject, Signal


@dataclass(frozen=True)
class _CueRef:
    track: Literal["video", "bgm", "sfx", "dialogue"]
    seg_index: int


class Selection(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._refs: set[_CueRef] = set()

    def get(self) -> list[_CueRef]:
        return sorted(self._refs, key=lambda r: (r.track, r.seg_index))

    def set(self, refs) -> None:
        new = set(refs)
        if new != self._refs:
            self._refs = new
            self.changed.emit()

    def add(self, ref: _CueRef) -> None:
        if ref not in self._refs:
            self._refs.add(ref)
            self.changed.emit()

    def toggle(self, ref: _CueRef) -> None:
        if ref in self._refs:
            self._refs.discard(ref)
        else:
            self._refs.add(ref)
        self.changed.emit()

    def clear(self) -> None:
        if self._refs:
            self._refs.clear()
            self.changed.emit()

    def by_track(self) -> dict:
        out: dict = {}
        for r in self._refs:
            out.setdefault(r.track, []).append(r.seg_index)
        return out
