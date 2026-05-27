"""AppShell：基于 qfluentwidgets.FluentWindow 的流程式外壳（Phase 1 spike）。

侧栏按 nav_config.PHASES 分阶段注册 7 个功能页（本任务为占位页，下个任务接真实 panel）。
"""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget
from qfluentwidgets import (
    FluentWindow, FluentIcon, NavigationItemPosition,
)
from drama_shot_master.ui.nav_config import FUNCS, PHASES, ICONS, LABELS


def _icon(key: str):
    """Resolve a nav_config ICONS string to a FluentIcon member.

    Falls back to FluentIcon.TAG if the name is not found in this version of
    qfluentwidgets (all current names verified present in 1.11.2; kept as
    safety net for future icon renames).
    """
    return getattr(FluentIcon, ICONS[key], FluentIcon.TAG)


class _Placeholder(QWidget):
    """Spike 占位页；下个任务替换为真实页。"""
    def __init__(self, key: str, parent=None):
        super().__init__(parent)
        # objectName MUST be unique — FluentWindow uses it as the route key.
        self.setObjectName(f"page_{key}")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(LABELS[key]))


class AppShell(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Drama-Shot-Master")
        self.resize(1360, 860)
        self.pages: dict[str, QWidget] = {}
        self._phase_of: dict[str, str] = {}
        self._build_nav()

    def _build_nav(self):
        for phase_title, keys in PHASES:
            # Phase section header: non-selectable label item.
            # addItem signature (verified against qfluentwidgets 1.11.2):
            #   addItem(routeKey, icon, text, onClick=None, selectable=True,
            #           position=TOP, tooltip=None, parentRouteKey=None)
            self.navigationInterface.addItem(
                routeKey=f"phase::{phase_title}",
                icon=FluentIcon.TAG,
                text=phase_title,
                onClick=None,
                selectable=False,
                position=NavigationItemPosition.SCROLL,
            )
            for key in keys:
                page = _Placeholder(key)
                self.pages[key] = page
                self._phase_of[key] = phase_title
                # addSubInterface signature (verified against 1.11.2):
                #   addSubInterface(interface, icon, text, position=TOP,
                #                   parent=None, isTransparent=False)
                self.addSubInterface(
                    page, _icon(key), LABELS[key],
                    position=NavigationItemPosition.SCROLL,
                )
            # Visual separator after each phase group.
            self.navigationInterface.addSeparator(
                position=NavigationItemPosition.SCROLL,
            )

    def _current_key(self) -> str:
        cur = self.stackedWidget.currentWidget()
        for key, page in self.pages.items():
            if page is cur:
                return key
        # Default to first functional key if nothing matches yet.
        return FUNCS[0][1]

    def breadcrumb_text(self) -> str:
        key = self._current_key()
        return f"{self._phase_of.get(key, '')} › {LABELS.get(key, '')}"

    def showEvent(self, e):
        super().showEvent(e)
        if not getattr(self, "_titlebar_themed", False):
            self._titlebar_themed = True
            from drama_shot_master.ui.theme import apply_dark_titlebar
            apply_dark_titlebar(self)
