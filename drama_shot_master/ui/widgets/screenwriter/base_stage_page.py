"""_BaseStagePage：4 个 wizard 阶段子面板的公共基类。

提供 3 个跨阶段信号 + set_project/try_release 抽象接口。
具体 UI 在子类 _build_ui 里建。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget


class _BaseStagePage(QWidget):
    """所有 wizard 子面板（IdeatePage/ScriptPage/...）的基类。

    子类必须实现：
      - set_project(path: Path | None) → 切项目时调；None=置占位
      - try_release() → bool；dirty 时返 False 阻断切阶段/切项目
    """
    stageAdvanceRequested = Signal(int)     # 推进到第几个阶段（0..3）
    projectStateChanged = Signal()          # 产物变化 → master 列表状态点要刷
    statusMessage = Signal(str)             # toast 到主窗状态栏

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self._client = client
        self._project_dir: Path | None = None

    def set_project(self, path: Path | None) -> None:
        raise NotImplementedError

    def try_release(self) -> bool:
        """默认无 dirty。子类有未保存编辑时 override 返 False 可阻断切换。"""
        return True
