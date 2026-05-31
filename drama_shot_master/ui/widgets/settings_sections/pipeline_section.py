"""流程 & 调试 section：流程锁开关（pipeline_lock_enabled）。

默认关=各阶段全可达，便于调试；开=按阶段顺序解锁（_sync_nav_gates 读此值）。
"""
from __future__ import annotations

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QCheckBox


class PipelineSection(QWidget):
    title = "流程 & 调试"
    category = "应用"

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.addWidget(QLabel("流程锁"))
        self.lock_cb = QCheckBox("启用流程锁（按阶段顺序解锁；关闭 = 各阶段全部可达，便于调试）")
        self.lock_cb.setChecked(bool(getattr(self._cfg, "pipeline_lock_enabled", False)))
        root.addWidget(self.lock_cb)
        hint = QLabel("关闭时可任意跳转阶段；开启后需按 创意→剧本→分镜→… 顺序完成解锁。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#9aa0a6;")
        root.addWidget(hint)
        root.addStretch(1)

    def load_from(self, cfg):
        self.lock_cb.setChecked(bool(getattr(cfg, "pipeline_lock_enabled", False)))

    def save_to(self, cfg):
        try:
            cfg.update_settings(pipeline_lock_enabled=self.lock_cb.isChecked())
        except Exception:
            pass

    def validate(self):
        return (True, "")

    def cancel_workers(self):
        pass
