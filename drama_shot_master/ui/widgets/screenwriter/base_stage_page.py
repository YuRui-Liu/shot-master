"""_BaseStagePage：4 个 wizard 阶段子面板的公共基类。

提供 3 个跨阶段信号 + worker dict 字段族 + 工具方法。
具体 UI 在子类 _build_ui 里建。

Worker dict 模式（spec §4.1）：所有 SSE worker 按 project_dir 索引，
切换项目不停别项目的 worker，UI 只显示当前 _project_dir 对应的状态。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget


class _BaseStagePage(QWidget):
    """所有 wizard 子面板（IdeatePage/ScriptPage/...）的基类。"""
    stageAdvanceRequested = Signal(int)     # 推进到第几个阶段（0..3）
    projectStateChanged = Signal()          # 产物变化 → master 列表状态点要刷
    statusMessage = Signal(str)             # toast 到主窗状态栏

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self._client = client
        self._project_dir: Path | None = None
        # 多项目并发支持：worker / 缓冲 / 状态 / 错误 按 project_dir 索引
        self._workers: dict[Path, object] = {}        # value: StreamWorker
        self._buf_by_project: dict[Path, str] = {}
        self._state_by_project: dict[Path, str] = {}  # idle/streaming/done/error
        self._error_by_project: dict[Path, str] = {}

    # —— 抽象 ——

    def set_project(self, path: Path | None) -> None:
        raise NotImplementedError

    def try_release(self) -> bool:
        """默认无 dirty。子类有未保存编辑时 override 返 False 可阻断切换。"""
        return True

    # —— 通用工具（给 TaskManager / 子类用）——

    def is_streaming(self, project_dir: Path) -> bool:
        w = self._workers.get(project_dir)
        return bool(w and w.isRunning())

    def _active_worker(self):
        if self._project_dir is None:
            return None
        return self._workers.get(self._project_dir)

    def _on_project_switched(self, old: Path | None, new: Path | None) -> None:
        """切换 hook。默认 no-op，子类可 override。"""
        pass
