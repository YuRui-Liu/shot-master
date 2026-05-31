"""StoryboardPage：分镜板合并页（纯容器）。

把「出图 / 拆图 / 拼图 / 裁边」四个工具收拢到一个顶部 QTabWidget 下。

本页只做容器：tab 装载 + 切换 + 当前 tab 访问器，**不构造具体 panel**。
那些 panel 需要 state/cfg，由 Wave2 的 app_shell 构造后通过
``set_tabs(items)`` 或构造参数传入。

API：
    set_tabs(items: list[(key, label, widget)]) —— 放入若干 tab
    current_key() -> str | None —— 当前选中 tab 的 key
"""
from __future__ import annotations

from typing import Iterable, Optional

from PySide6.QtWidgets import QWidget, QVBoxLayout, QTabWidget


class StoryboardPage(QWidget):
    """分镜板合并页：顶部 QTabWidget 容器。"""

    def __init__(self, items: Optional[Iterable[tuple]] = None, parent=None):
        super().__init__(parent)

        # 顶部 tab 容器
        self.tabs = QTabWidget(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.tabs)

        # key 列表与 tab 索引一一对应，便于 current_key() 反查
        self._keys: list[str] = []

        if items is not None:
            self.set_tabs(items)

    # ── tab 装载 ──────────────────────────────────────────────────────────
    def set_tabs(self, items: Iterable[tuple]) -> None:
        """放入一组 (key, label, widget)；会清空旧 tab。

        默认选中第 0 个（出图）。
        """
        self.tabs.clear()
        self._keys = []
        for key, label, widget in items:
            self.tabs.addTab(widget, label)
            self._keys.append(key)
        if self.tabs.count():
            self.tabs.setCurrentIndex(0)

    # ── 访问器 ────────────────────────────────────────────────────────────
    def current_key(self) -> Optional[str]:
        """当前选中 tab 的 key；无 tab 时返回 None。"""
        idx = self.tabs.currentIndex()
        if 0 <= idx < len(self._keys):
            return self._keys[idx]
        return None

    def set_current_tab(self, key: str) -> None:
        """按 key 切到对应 tab；未知 key 静默忽略（不抛）。"""
        if key in self._keys:
            self.tabs.setCurrentIndex(self._keys.index(key))
