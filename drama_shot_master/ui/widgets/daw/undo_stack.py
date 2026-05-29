"""撤销栈：max depth 100；每 push 自动 execute。"""
from __future__ import annotations
from PySide6.QtCore import QObject, Signal


class UndoStack(QObject):
    canUndoChanged = Signal(bool)
    canRedoChanged = Signal(bool)
    MAX_DEPTH = 100

    def __init__(self, parent=None):
        super().__init__(parent)
        self._past: list = []
        self._future: list = []

    def push(self, cmd) -> None:
        cmd.execute()
        self._past.append(cmd)
        if len(self._past) > self.MAX_DEPTH:
            self._past.pop(0)
        self._future.clear()
        self.canUndoChanged.emit(self.can_undo())
        self.canRedoChanged.emit(self.can_redo())

    def undo(self) -> None:
        if not self._past:
            return
        cmd = self._past.pop()
        cmd.undo()
        self._future.append(cmd)
        self.canUndoChanged.emit(self.can_undo())
        self.canRedoChanged.emit(self.can_redo())

    def redo(self) -> None:
        if not self._future:
            return
        cmd = self._future.pop()
        cmd.redo()
        self._past.append(cmd)
        self.canUndoChanged.emit(self.can_undo())
        self.canRedoChanged.emit(self.can_redo())

    def can_undo(self) -> bool:
        return bool(self._past)

    def can_redo(self) -> bool:
        return bool(self._future)

    def clear(self) -> None:
        self._past.clear()
        self._future.clear()
        self.canUndoChanged.emit(False)
        self.canRedoChanged.emit(False)
