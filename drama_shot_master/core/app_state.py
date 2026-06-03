"""全局 UI 状态 + 目录记忆。

不依赖 PySide6（纯数据 + drama_shot_master.imaging），可单测。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from drama_shot_master.imaging.loader import load_directory, ImageInfo

from drama_shot_master.config import Config


@dataclass
class AppState:
    # ---- 批处理态（拆/拼/裁 scope）：load_dir 维护，勿与项目 scope 混用 ----
    current_dir: Optional[Path] = None
    images: list[ImageInfo] = field(default_factory=list)
    selected: list[int] = field(default_factory=list)  # 含点击顺序
    output_dir: Optional[Path] = None
    active_function: str = "inference"  # inference|split|combine|trim

    # ---- 项目态（罗盘 scope）：load_project 维护，与批处理态物理分离 ----
    current_project_dir: Optional[Path] = None
    current_project_id: Optional[str] = None
    # 四阶段 state（screenwriter/assets/storyboard/production → pending|in_progress|completed）
    pipeline_state: dict[str, str] = field(default_factory=dict)
    # 四阶段 next_action 文案（阶段名 → 下一步建议）
    next_action: dict[str, str] = field(default_factory=dict)

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

    def load_project(self, root: Path) -> None:
        """加载项目 scope（罗盘）：回填 current_project_dir/id/pipeline_state/next_action。

        有 project.json → compass.load_manifest；无 → compass.migrate_project_dir。
        缺失/坏目录 → 静默降级（项目态保持 None/空），不抛。
        **与 load_dir() / current_dir 等批处理态完全无关（物理分离）。**
        """
        # 延迟导入：避免 state 模块加载时硬依赖 compass（保持 Qt-free 轻量）
        from drama_shot_master.core.compass.manifest import load_manifest
        from drama_shot_master.core.compass.migrate import migrate_project_dir
        from drama_shot_master.core.compass.paths import manifest_path

        if root is None:
            return
        root = Path(root)
        if not root.is_dir():
            return

        try:
            if manifest_path(root).is_file():
                manifest = load_manifest(root)
            else:
                manifest = migrate_project_dir(root)
        except Exception:
            # 坏目录/迁移异常 → 降级不崩，项目态维持原样
            return

        self.current_project_dir = root
        self.current_project_id = manifest.project_id or None
        self.pipeline_state = {
            name: st.state for name, st in manifest.pipeline.items()
        }
        self.next_action = {
            name: st.next_action
            for name, st in manifest.pipeline.items()
            if st.next_action
        }

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
