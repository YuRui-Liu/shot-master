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

    def is_streaming(self, project_dir: Path, episode_id: str | None = None) -> bool:
        """支持两种 key 形态：
          - Path-only（IdeatePage 等无集语义的 stage）
          - (Path, episode_id)（多集 stage）
        episode_id is None 时返「项目级任一 streaming」。
        """
        if episode_id is not None:
            w = self._workers.get((project_dir, episode_id))
            if w and w.isRunning():
                return True
            return False
        # 项目级聚合：先查 Path-only key，再查所有 tuple key
        w = self._workers.get(project_dir)
        if w and w.isRunning():
            return True
        for k, w in self._workers.items():
            if isinstance(k, tuple) and len(k) == 2 and k[0] == project_dir:
                if w and w.isRunning():
                    return True
        return False

    def _active_worker(self):
        if self._project_dir is None:
            return None
        return self._workers.get(self._project_dir)

    def _on_project_switched(self, old: Path | None, new: Path | None) -> None:
        """切换 hook。默认 no-op，子类可 override。"""
        pass

    def start_generation_if_idle(self) -> None:
        """stageAdvanceRequested 触发——上一个阶段「推进」后，本阶段自动跑起来。
        子类 override：上游产物存在 + 本阶段产物不存在 + state idle → 调 _on_generate_clicked。
        默认 no-op（IdeatePage 创意阶段总要先填 context，不是从上游自动 trigger 的）。"""
        pass
