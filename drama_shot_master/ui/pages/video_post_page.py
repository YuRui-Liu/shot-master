"""VideoPostPage：视频后期合并页（纯容器）。

把后期阶段的「配音 / 配乐」收拢为一个 QTabWidget 容器页。与 C-1 同风格：
本页不构造任何具体 panel，只负责承载外部传入的 widget、做 tab 切换，并通过
current_key() 暴露当前激活页签的稳定 key。具体面板由 Wave2 接线时注入。

配乐为项目级配置（一个项目共用一套配乐方案），故其页签标题带「项目级」小标注。
"""
from __future__ import annotations

from typing import Iterable, Tuple

from PySide6.QtWidgets import QWidget, QVBoxLayout, QTabWidget

# (key, 标题, widget)：key 为稳定标识，标题为展示文本，widget 为内容控件
TabItem = Tuple[str, str, QWidget]

# 项目级配置的 key → 标题追加小标注，提示该页签作用于整个项目而非单集
_PROJECT_LEVEL_KEYS = {"soundtrack"}


class VideoPostPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._keys: list[str] = []

        self.tabs = QTabWidget(self)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.tabs)

    def set_tabs(self, items: Iterable[TabItem]) -> None:
        """重置页签：清空后按 items 顺序放入。幂等——重复调用结果一致。"""
        self.tabs.clear()
        self._keys = []
        for key, title, widget in items:
            label = title
            if key in _PROJECT_LEVEL_KEYS:
                label = f"{title}（项目级）"
            self.tabs.addTab(widget, label)
            self._keys.append(key)

    def current_key(self) -> str:
        """当前激活页签的稳定 key；无页签时返回空串。"""
        idx = self.tabs.currentIndex()
        if 0 <= idx < len(self._keys):
            return self._keys[idx]
        return ""

    def set_current_tab(self, key: str) -> None:
        """按 key 切到对应页签；未知 key 静默忽略（不抛）。"""
        if key in self._keys:
            self.tabs.setCurrentIndex(self._keys.index(key))
