"""功能面板抽象基类。每个面板自带参数表单，向 MainWindow 暴露统一接口。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from app.config import Config
from app.ui.state import AppState


class BasePanel(QWidget):
    """子类必须实现 validate/execute/select_mode；可选 preview。"""
    statusMessage = Signal(str)        # 发到状态栏
    validityChanged = Signal()         # 参数变化 → MainWindow 重算执行按钮

    def __init__(self, state: AppState, cfg: Config, parent=None):
        super().__init__(parent)
        self.state = state
        self.cfg = cfg

    def select_mode(self) -> str:
        """中栏选择模式：'multi' 或 'order'。"""
        return "multi"

    def validate(self) -> tuple[bool, str]:
        """返回 (可执行?, 原因)。原因在不可执行时显示。"""
        return False, "未实现"

    def execute(self) -> None:
        """执行操作。耗时操作子类自行起 QThread。"""
        raise NotImplementedError

    def preview(self) -> None:
        """可选预览。默认无。"""
        pass

    def has_preview(self) -> bool:
        return False

    def overlay_spec(self) -> dict | None:
        """拆图功能用：返回 overlay 参数 dict；其它面板返回 None。"""
        return None
