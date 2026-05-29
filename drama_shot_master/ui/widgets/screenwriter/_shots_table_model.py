"""分镜 shots 列表的 QAbstractTableModel 包装。

列：ID | 时长(s) | 构图 | 描述 | stylePrompt。
setData 直接改 self._shots[i][key]——shots 是 storyboard_page._sb["shots"] 的引用，
所以外层 _sb 同步更新。"""
from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


_COLS = (
    ("shotId",      "ID"),
    ("duration",    "时长(s)"),
    ("composition", "构图"),
    ("description", "描述"),
    ("stylePrompt", "stylePrompt"),
)


class _ShotsTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._shots: list[dict] = []

    def set_shots(self, shots: list[dict]) -> None:
        self.beginResetModel()
        self._shots = shots
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._shots)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(_COLS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole or orientation != Qt.Horizontal:
            return None
        return _COLS[section][1] if 0 <= section < len(_COLS) else None

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or role not in (Qt.DisplayRole, Qt.EditRole):
            return None
        key, _ = _COLS[index.column()]
        return str(self._shots[index.row()].get(key, ""))

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid() or role != Qt.EditRole:
            return False
        key, _ = _COLS[index.column()]
        # duration 是数字
        if key == "duration":
            try:
                value = float(value)
            except (ValueError, TypeError):
                return False
        self._shots[index.row()][key] = value
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        return True
