"""分镜图提示词 — 手动分组编辑器 + 纯函数。

纯函数无 Qt 依赖，便于单测；_GridGroupEditor 是表格 UI（后续任务追加）。
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QComboBox, QPushButton, QLabel, QHeaderView,
)

_MODE_LABELS = [("single", "单帧"), ("4", "四宫格"), ("9", "九宫格")]
_CAP = {"single": 1, "4": 4, "9": 9}


def group_capacity(grid_mode: str) -> int:
    return _CAP.get(grid_mode, 9)


def auto_fit_mode(count: int) -> str:
    """容纳 count 镜的最小容量模式。"""
    if count <= 1:
        return "single"
    if count <= 4:
        return "4"
    return "9"


def default_groups(shot_ids: list[str]) -> list[dict]:
    """按 9 切块；每组 grid_mode = auto_fit_mode(组镜头数)。"""
    out: list[dict] = []
    for i in range(0, len(shot_ids), 9):
        chunk = shot_ids[i:i + 9]
        out.append({"grid_mode": auto_fit_mode(len(chunk)),
                    "shot_ids": list(chunk)})
    return out


def group_is_valid(group: dict) -> bool:
    ids = group.get("shot_ids") or []
    return 0 < len(ids) <= group_capacity(group.get("grid_mode", "9"))


class _GridGroupEditor(QWidget):
    """分组表格：组 | 起始 | 结束 | 模式 | 生成 | 状态 + 添加组 / 全部生成。"""

    generateGroup = Signal(int)   # 1-based 组序号
    generateAll = Signal()
    groupsChanged = Signal()

    _COL_LABEL, _COL_START, _COL_END, _COL_MODE, _COL_GEN, _COL_STATUS = range(6)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._shot_ids: list[str] = []
        self._groups: list[dict] = []
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        v.addWidget(QLabel("分组："))
        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["组", "起始", "结束", "模式", "生成", "状态"])
        h = self._table.horizontalHeader()
        h.setSectionResizeMode(self._COL_START, QHeaderView.Stretch)
        h.setSectionResizeMode(self._COL_END, QHeaderView.Stretch)
        self._table.verticalHeader().setVisible(False)
        v.addWidget(self._table)
        bar = QHBoxLayout()
        add_btn = QPushButton("+ 添加组")
        add_btn.clicked.connect(self._add_group)
        bar.addWidget(add_btn)
        bar.addStretch(1)
        self._gen_all_btn = QPushButton("全部生成")
        self._gen_all_btn.clicked.connect(lambda: self.generateAll.emit())
        bar.addWidget(self._gen_all_btn)
        v.addLayout(bar)

    # —— 公共 API ——

    def set_shots(self, shot_ids: list[str]) -> None:
        self._shot_ids = list(shot_ids)
        self._groups = default_groups(self._shot_ids)
        self._rebuild()

    def groups(self) -> list[dict]:
        return [dict(g) for g in self._groups]

    def set_group_status(self, index: int, status: str) -> None:
        """index 1-based；status: idle/running/done/error。"""
        r = index - 1
        if 0 <= r < self._table.rowCount():
            it = self._table.item(r, self._COL_STATUS)
            glyph = {"idle": "○", "running": "●", "done": "✓",
                     "error": "✗"}.get(status, "○")
            if it:
                it.setText(glyph)

    # —— 内部 ——

    def _emit_generate_group(self, index: int) -> None:
        self.generateGroup.emit(index)

    def _add_group(self) -> None:
        first = self._shot_ids[0] if self._shot_ids else ""
        self._groups.append({"grid_mode": "single",
                             "shot_ids": [first] if first else []})
        self._rebuild()
        self.groupsChanged.emit()

    def _slice_ids(self, start_id: str, end_id: str) -> list[str]:
        try:
            i = self._shot_ids.index(start_id)
            j = self._shot_ids.index(end_id)
        except ValueError:
            return []
        if j < i:
            i, j = j, i
        return self._shot_ids[i:j + 1]

    def _mk_combo(self, items, current) -> QComboBox:
        c = QComboBox()
        for data, label in items:
            c.addItem(label, data)
        idx = c.findData(current)
        if idx >= 0:
            c.setCurrentIndex(idx)
        return c

    def _rebuild(self) -> None:
        self._table.setRowCount(0)
        for gi, g in enumerate(self._groups, start=1):
            r = self._table.rowCount()
            self._table.insertRow(r)
            self._table.setItem(r, self._COL_LABEL, QTableWidgetItem(f"S{gi}"))
            ids = g.get("shot_ids") or []
            start_id = ids[0] if ids else (self._shot_ids[0] if self._shot_ids else "")
            end_id = ids[-1] if ids else start_id
            start_combo = self._mk_combo([(s, s) for s in self._shot_ids], start_id)
            end_combo = self._mk_combo([(s, s) for s in self._shot_ids], end_id)
            mode_combo = self._mk_combo(_MODE_LABELS, g.get("grid_mode", "9"))
            start_combo.currentIndexChanged.connect(
                lambda _=0, row=r: self._on_row_changed(row))
            end_combo.currentIndexChanged.connect(
                lambda _=0, row=r: self._on_row_changed(row))
            mode_combo.currentIndexChanged.connect(
                lambda _=0, row=r: self._on_row_changed(row))
            self._table.setCellWidget(r, self._COL_START, start_combo)
            self._table.setCellWidget(r, self._COL_END, end_combo)
            self._table.setCellWidget(r, self._COL_MODE, mode_combo)
            gen_btn = QPushButton("▶")
            gen_btn.setMinimumWidth(40)
            gen_btn.clicked.connect(
                lambda _=False, idx=gi: self._emit_generate_group(idx))
            self._table.setCellWidget(r, self._COL_GEN, gen_btn)
            valid = group_is_valid(g)
            st = QTableWidgetItem("○" if valid else "✗ 超容量")
            self._table.setItem(r, self._COL_STATUS, st)
            gen_btn.setEnabled(valid)

    def _on_row_changed(self, row: int) -> None:
        if not (0 <= row < len(self._groups)):
            return
        sc = self._table.cellWidget(row, self._COL_START)
        ec = self._table.cellWidget(row, self._COL_END)
        mc = self._table.cellWidget(row, self._COL_MODE)
        if sc is None or ec is None or mc is None:
            return
        self._groups[row] = {
            "grid_mode": mc.currentData(),
            "shot_ids": self._slice_ids(sc.currentData(), ec.currentData()),
        }
        valid = group_is_valid(self._groups[row])
        st = self._table.item(row, self._COL_STATUS)
        if st:
            st.setText("○" if valid else "✗ 超容量")
        gb = self._table.cellWidget(row, self._COL_GEN)
        if gb:
            gb.setEnabled(valid)
        self.groupsChanged.emit()
