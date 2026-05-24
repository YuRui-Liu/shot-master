"""全局 UI 状态 + 目录记忆。

不依赖 PySide6（纯数据 + shot-master core），可单测。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from shot_master.core.loader import load_directory, ImageInfo

from drama_shot_master.config import Config


@dataclass
class AppState:
    current_dir: Optional[Path] = None
    images: list[ImageInfo] = field(default_factory=list)
    selected: list[int] = field(default_factory=list)  # 含点击顺序
    output_dir: Optional[Path] = None
    active_function: str = "inference"  # inference|split|combine|trim

    def load_dir(self, directory: Path) -> None:
        """加载目录图片。目录不存在则清空（静默）。"""
        directory = Path(directory)
        if not directory.is_dir():
            self.current_dir = None
            self.images = []
            self.selected = []
            return
        self.current_dir = directory
        self.images = load_directory(directory)
        self.selected = []

    def selected_paths(self) -> list[Path]:
        return [self.images[i].path for i in self.selected
                if 0 <= i < len(self.images)]


def restore_from_config(state: AppState, cfg: Config) -> None:
    """启动时按 cfg 的 last_input_dir/last_output_dir 回填。路径失效静默忽略。"""
    if cfg.last_input_dir:
        p = Path(cfg.last_input_dir)
        if p.is_dir():
            state.load_dir(p)
    if cfg.last_output_dir:
        p = Path(cfg.last_output_dir)
        if p.is_dir():
            state.output_dir = p


def remember_dirs(state: AppState, cfg: Config) -> None:
    """把当前目录/输出目录写回 settings.json。"""
    cfg.update_settings(
        last_input_dir=str(state.current_dir) if state.current_dir else None,
        last_output_dir=str(state.output_dir) if state.output_dir else None,
    )
