# drama_shot_master/ui/pages/welcome_page.py
"""欢迎首页：全画布深蓝紫调，Logo+Hero+最近项目卡片+工作流条。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtGui import (
    QPainter, QColor, QLinearGradient, QRadialGradient, QBrush,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QGraphicsDropShadowEffect,
)

from drama_shot_master.core.recent_projects import RecentProjectsManager
from drama_shot_master.ui.widgets.workflow_strip import WorkflowStrip
from drama_shot_master.ui.widgets.project_card import ProjectCard

_MAX_CARDS = 4


class WelcomePage(QWidget):
    """欢迎首页。与 AppShell 通信通过信号，不持有 AppShell 引用。"""

    project_selected = Signal(str)
    new_project_requested = Signal()
    open_dir_requested = Signal()
    settings_requested = Signal()

    def __init__(self, recent_mgr: RecentProjectsManager,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._mgr = recent_mgr
        self.setObjectName("WelcomePage")
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._make_nav_bar())
        root.addWidget(self._make_hero())

        self._cards_area = self._make_cards_area()
        root.addWidget(self._cards_area, 1)

        self._pagination = self._make_pagination()
        root.addWidget(self._pagination)

        root.addWidget(WorkflowStrip(active_index=0))

    def _make_nav_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("WelcomeNavBar")
        bar.setFixedHeight(42)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(8)

        icon_lbl = QLabel()
        icon_lbl.setObjectName("WelcomeAppIcon")
        icon_lbl.setFixedSize(20, 20)
        lay.addWidget(icon_lbl)

        name_lbl = QLabel("糯米 AI")
        name_lbl.setObjectName("WelcomeAppName")
        lay.addWidget(name_lbl)

        lay.addStretch(1)

        settings_btn = QPushButton("⚙  全局设置")
        settings_btn.setObjectName("WelcomeSettingsBtn")
        settings_btn.setFixedHeight(26)
        settings_btn.clicked.connect(self.settings_requested)
        lay.addWidget(settings_btn)

        return bar

    def _make_hero(self) -> QWidget:
        hero = QWidget()
        hero.setObjectName("WelcomeHero")
        lay = QVBoxLayout(hero)
        lay.setContentsMargins(0, 24, 0, 16)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignCenter)

        title = QLabel("糯米AI分镜影视创作台")
        title.setObjectName("WelcomeTitle")
        title.setAlignment(Qt.AlignCenter)
        # 蓝色辉光（近似 mockup 的 text-shadow 0 0 40px rgba(74,158,255,.25)）
        title_glow = QGraphicsDropShadowEffect(title)
        title_glow.setBlurRadius(40)
        title_glow.setOffset(0, 0)
        title_glow.setColor(QColor(74, 158, 255, 110))
        title.setGraphicsEffect(title_glow)
        lay.addWidget(title)

        subtitle = QLabel("剧本 · 分镜 · 视频 · 后期配音配乐")
        subtitle.setObjectName("WelcomeSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        lay.addWidget(subtitle)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.setAlignment(Qt.AlignCenter)

        self._btn_new = QPushButton("＋  新建项目")
        self._btn_new.setObjectName("WelcomeBtnPrimary")
        self._btn_new.setFixedHeight(36)
        self._btn_new.clicked.connect(self.new_project_requested)
        btn_row.addWidget(self._btn_new)

        self._btn_open = QPushButton("打开目录")
        self._btn_open.setObjectName("WelcomeBtnSecondary")
        self._btn_open.setFixedHeight(36)
        self._btn_open.clicked.connect(self.open_dir_requested)
        btn_row.addWidget(self._btn_open)

        lay.addLayout(btn_row)
        return hero

    def _make_cards_area(self) -> QWidget:
        w = QWidget()
        w.setObjectName("WelcomeCardsArea")
        self._cards_layout = QHBoxLayout(w)
        self._cards_layout.setContentsMargins(24, 0, 24, 0)
        self._cards_layout.setSpacing(12)
        return w

    def _make_pagination(self) -> QWidget:
        w = QWidget()
        w.setObjectName("WelcomePagination")
        w.setFixedHeight(18)
        self._page_layout = QHBoxLayout(w)
        self._page_layout.setContentsMargins(0, 4, 0, 4)
        self._page_layout.setSpacing(5)
        self._page_layout.setAlignment(Qt.AlignCenter)
        return w

    def refresh(self) -> None:
        """从 RecentProjectsManager 重新加载最近项目并重建卡片区。"""
        projects = self._mgr.load()
        self._rebuild_cards(projects)
        self._rebuild_pagination(projects)

    def _rebuild_cards(self, projects: list[dict]) -> None:
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not projects:
            empty = QLabel("创建你的第一个项目")
            empty.setObjectName("WelcomeEmptyHint")
            empty.setAlignment(Qt.AlignCenter)
            self._cards_layout.addWidget(empty)
            add_card = ProjectCard(None, depth="add", is_add_button=True)
            add_card.clicked.connect(lambda _: self.new_project_requested.emit())
            self._cards_layout.addWidget(add_card, 1, Qt.AlignVCenter)
            self._apply_card_heights()
            return

        show = projects[:_MAX_CARDS]
        if len(show) == 1:
            depths = ["center"]
        elif len(show) == 2:
            depths = ["near", "center"]
        elif len(show) == 3:
            depths = ["far", "near", "center"]
        else:
            depths = ["far", "near", "center", "near"]

        stretch_map = {"far": 65, "near": 85, "center": 140}

        for i, (proj, depth) in enumerate(zip(show, depths)):
            card = ProjectCard(proj, depth=depth, color_index=i)
            card.clicked.connect(self._on_card_clicked)
            # 垂直居中 → 矮卡浮在中线，配合高度比例形成景深阶梯
            self._cards_layout.addWidget(card, stretch_map.get(depth, 85), Qt.AlignVCenter)

        add_card = ProjectCard(None, depth="add", is_add_button=True)
        add_card.clicked.connect(lambda _: self.new_project_requested.emit())
        self._cards_layout.addWidget(add_card, 50, Qt.AlignVCenter)
        self._apply_card_heights()

    def _rebuild_pagination(self, projects: list[dict]) -> None:
        while self._page_layout.count():
            item = self._page_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        count = min(len(projects), _MAX_CARDS)
        if count == 0:
            return
        for i in range(count):
            dot = QLabel()
            dot.setObjectName("PageDotActive" if i == 0 else "PageDot")
            dot.setFixedSize(16 if i == 0 else 6, 6)
            self._page_layout.addWidget(dot)

    def _on_card_clicked(self, path: str) -> None:
        if path:
            self.project_selected.emit(path)
        else:
            self.new_project_requested.emit()

    def _apply_card_heights(self) -> None:
        """按各卡 depth 高度比例设定固定高度，配合 AlignVCenter 形成景深阶梯。"""
        avail = self._cards_area.height()
        if avail <= 0:
            return
        for i in range(self._cards_layout.count()):
            card = self._cards_layout.itemAt(i).widget()
            if isinstance(card, ProjectCard):
                card.setFixedHeight(max(1, int(avail * card.height_ratio())))

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._apply_card_heights()

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        bg = QLinearGradient(0, 0, w, h)
        bg.setColorAt(0.0, QColor("#0d1020"))
        bg.setColorAt(0.45, QColor("#08090f"))
        bg.setColorAt(1.0, QColor("#100820"))
        p.fillRect(self.rect(), QBrush(bg))

        top_glow = QRadialGradient(w / 2, 0, w * 0.45)
        top_glow.setColorAt(0.0, QColor(74, 158, 255, 35))
        top_glow.setColorAt(0.5, QColor(160, 108, 255, 12))
        top_glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(QRect(int(w * 0.05), -80, int(w * 0.9), 280), QBrush(top_glow))

        bl_glow = QRadialGradient(int(w * 0.2), h - 40, int(w * 0.25))
        bl_glow.setColorAt(0.0, QColor(160, 108, 255, 20))
        bl_glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(QRect(0, int(h * 0.55), int(w * 0.5), int(h * 0.5)), QBrush(bl_glow))

        br_glow = QRadialGradient(int(w * 0.85), h - 20, int(w * 0.2))
        br_glow.setColorAt(0.0, QColor(74, 158, 255, 15))
        br_glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(QRect(int(w * 0.6), int(h * 0.6), int(w * 0.45), int(h * 0.45)),
                   QBrush(br_glow))
        p.end()
