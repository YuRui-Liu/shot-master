"""产物树：按 _sb 推算预期文件 + 已落盘文件状态点。"""
from __future__ import annotations

from math import ceil
from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem


_STATUS_GLYPHS = {"missing": "○", "streaming": "●", "done": "✓"}
_STATUS_COLORS = {
    "missing":   "#9aa0a6",
    "streaming": "#4a9eff",
    "done":      "#4ec98f",
}


class _ProductTree(QTreeWidget):
    fileActivated = Signal(object)        # Path

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.itemDoubleClicked.connect(self._on_double_clicked)
        self.tree_items: dict[Path, QTreeWidgetItem] = {}

    def build_from_sb(self, prompts_dir: Path, sb: dict,
                      *, grid_mode: str = "9",
                      groups: list | None = None,
                      include_character_refs: bool,
                      episode_id: str = ""):
        """按分镜.json 推算预期文件，构建树 + 状态点。
        groups 非空时按组数渲染 N宫格/S{k}.md；否则按 grid_mode 统一切块。"""
        self.clear()
        self.tree_items = {}
        if include_character_refs:
            characters = sb.get("characters") or []
            char_group = QTreeWidgetItem(self,
                [f"📁 角色参考图 ({len(characters)})"])
            char_group.setExpanded(True)
            for ch in characters:
                name = ch.get("name", "")
                if not name:
                    continue
                p = prompts_dir / "角色参考图" / f"{name}_ref.md"
                status = "done" if p.is_file() else "missing"
                self._add_file_item(char_group, p, status)
        # 网格
        shots = sb.get("shots") or []
        if groups:
            n_groups = len(groups)
        else:
            grid_size = {"single": 1, "4": 4, "9": 9}.get(grid_mode, 9)
            n_groups = ceil(len(shots) / grid_size) if shots else 0
        grid_group = QTreeWidgetItem(self, [f"📁 N 宫格 ({n_groups})"])
        grid_group.setExpanded(True)
        for i in range(1, n_groups + 1):
            p = prompts_dir / "N宫格" / f"S{i}.md"
            status = "done" if p.is_file() else "missing"
            self._add_file_item(grid_group, p, status)

    def _add_file_item(self, parent: QTreeWidgetItem, path: Path, status: str):
        text = f"{_STATUS_GLYPHS[status]}  {path.name}"
        it = QTreeWidgetItem(parent, [text])
        it.setData(0, Qt.UserRole, str(path))
        self.tree_items[path] = it

    def set_status(self, path: Path, status: str) -> None:
        if path not in self.tree_items:
            return
        it = self.tree_items[path]
        glyph = _STATUS_GLYPHS.get(status, "○")
        it.setText(0, f"{glyph}  {path.name}")

    def _on_double_clicked(self, item: QTreeWidgetItem, _col: int):
        path_str = item.data(0, Qt.UserRole)
        if path_str:
            self.fileActivated.emit(Path(path_str))
