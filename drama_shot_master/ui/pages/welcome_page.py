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
from drama_shot_master.ui.widgets.capsule_button import CapsuleButton

_MAX_CARDS = 4

# 各 depth 的相对宽度（flex），与 fullmockup.html 一致
_DEPTH_FLEX = {"far": 0.65, "near": 0.85, "center": 1.4, "add": 0.5}
# 中心卡的宽高比（竖向缩略图，w/h）；其余卡按 flex 比例推宽度
_CENTER_ASPECT = 0.64
# 卡片间距（与 _cards_layout spacing 保持一致）
_CARD_GAP = 14
# 中心卡最大高度上限：防止在 HiDPI/大屏上卡片过大（手动定位下不影响窗口最小宽，
# 仅用于视觉比例控制，避免卡片过分巨大）
_MAX_CENTER_H = 640
# 卡片区左右安全边距
_CARDS_MARGIN = 24


class WelcomePage(QWidget):
    """欢迎首页。与 AppShell 通信通过信号，不持有 AppShell 引用。"""

    project_selected = Signal(str)
    new_project_requested = Signal()
    open_dir_requested = Signal()
    settings_requested = Signal()

    def __init__(self, recent_mgr: RecentProjectsManager,
                 parent: QWidget | None = None,
                 registry=None):
        super().__init__(parent)
        self._mgr = recent_mgr
        # R2-5 阶段B（双轨过渡）：可选 compass.registry 数据源。
        # 有项目时优先用 registry（含 project_id）；空/不可用时降级回 recent_mgr。
        # 默认 None → 行为与旧版完全一致（仅走 recent_mgr.load()）。
        self._registry = registry
        self.setObjectName("WelcomePage")
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 旧 nav bar（糯米AI + 全局设置）已被全局无边框标题栏 FramelessTitleBar 取代，
        # 不再在欢迎页内渲染——避免与窗口标题栏双栏叠加。hero 直接作为欢迎页顶部。
        # _make_nav_bar 暂保留（兼容历史引用），但不挂入布局。
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
        lay.setContentsMargins(0, 28, 0, 24)
        lay.setSpacing(10)
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

        lay.addSpacing(10)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.setAlignment(Qt.AlignCenter)

        self._btn_new = CapsuleButton("＋  新建项目", variant="primary")
        self._btn_new.setObjectName("WelcomeBtnPrimary")
        self._btn_new.setFixedHeight(40)
        self._btn_new.setMinimumWidth(150)
        self._btn_new.clicked.connect(self.new_project_requested)
        btn_row.addWidget(self._btn_new)

        self._btn_open = CapsuleButton("打开目录", variant="secondary")
        self._btn_open.setObjectName("WelcomeBtnSecondary")
        self._btn_open.setFixedHeight(40)
        self._btn_open.setMinimumWidth(120)
        self._btn_open.clicked.connect(self.open_dir_requested)
        btn_row.addWidget(self._btn_open)

        lay.addLayout(btn_row)
        return hero

    def _make_cards_area(self) -> QWidget:
        # 卡片用手动 setGeometry 定位（聚焦卡居中），不用布局：
        # 这样焦点卡可精确锚定到画布水平中线，且卡片不会把窗口最小宽度撑大。
        w = QWidget()
        w.setObjectName("WelcomeCardsArea")
        self._cards = []
        self._hint = None
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
        """重新加载项目并重建卡片区。

        数据源优先 compass.registry.list_projects()（含 project_id）；
        registry 空/不可用时降级回 recent_mgr.load()（双轨过渡，防漂移）。
        """
        projects = self._load_projects()
        self._rebuild_cards(projects)
        self._rebuild_pagination(projects)

    def _load_projects(self) -> list[dict]:
        """挑选数据源：registry 有项目→registry；否则→recent_mgr。

        registry 调用任意异常/返回空 → 静默降级，保证首页永不因数据源崩。
        registry 摘要字段（project_name/path/...）归一化为 ProjectCard 期望的
        {name, path, last_opened, shot_count, project_id} 形状。
        """
        if self._registry is not None:
            try:
                summaries = self._registry.list_projects()
            except Exception:
                summaries = None
            if summaries:
                return [self._summary_to_card(s) for s in summaries]
        return self._mgr.load()

    @staticmethod
    def _summary_to_card(summary: dict) -> dict:
        """registry 摘要 → ProjectCard 卡片字典（保留 project_id）。"""
        s = summary or {}
        return {
            "name": s.get("project_name") or s.get("name") or "",
            "path": s.get("path") or s.get("dir") or "",
            "last_opened": s.get("last_modified") or s.get("last_opened") or "",
            "shot_count": s.get("shot_count") or s.get("episode_count") or 0,
            "project_id": s.get("project_id"),
        }

    def _rebuild_cards(self, projects: list[dict]) -> None:
        # 删除旧的自由子控件（卡片 + 空状态提示）
        for c in self._cards:
            c.setParent(None)
            c.deleteLater()
        self._cards = []
        if self._hint is not None:
            self._hint.setParent(None)
            self._hint.deleteLater()
            self._hint = None

        if not projects:
            # 空状态：引导文案 + 新建虚线卡，均居中（提示在加号卡正上方）
            self._hint = QLabel("创建你的第一个项目", self._cards_area)
            self._hint.setObjectName("WelcomeEmptyHint")
            self._hint.setAlignment(Qt.AlignCenter)
            self._hint.show()
            add_card = ProjectCard(None, depth="add", is_add_button=True,
                                   parent=self._cards_area)
            add_card.clicked.connect(lambda _: self.new_project_requested.emit())
            add_card.show()
            self._cards.append(add_card)
            self._relayout_cards()
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

        for i, (proj, depth) in enumerate(zip(show, depths)):
            card = ProjectCard(proj, depth=depth, color_index=i,
                               parent=self._cards_area)
            card.clicked.connect(self._on_card_clicked)
            card.show()
            self._cards.append(card)

        add_card = ProjectCard(None, depth="add", is_add_button=True,
                               parent=self._cards_area)
        add_card.clicked.connect(lambda _: self.new_project_requested.emit())
        add_card.show()
        self._cards.append(add_card)
        self._relayout_cards()

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

    def _relayout_cards(self) -> None:
        """手动定位卡片：焦点卡(center)锚定到画布水平中线，形成居中景深走马灯。

        - 高度 = 中心卡高 × depth 高度比例；中心卡高 = min(可用高, 上限)
        - 宽度 = (center 宽 / center flex) × depth flex；center 宽由 _CENTER_ASPECT 决定
        - 焦点卡中点对齐画布中线（而非整组居中）→ 单/多项目下项目卡都视觉居中
        - 各卡垂直居中；空状态提示居中显示在加号卡正上方
        """
        cards = [c for c in self._cards if c is not None]
        if not cards:
            return
        aw = self._cards_area.width()
        ah = self._cards_area.height()
        if aw <= 0 or ah <= 0:
            return

        avail_w = aw - 2 * _CARDS_MARGIN
        center_h = min(ah - 16, _MAX_CENTER_H)
        center_w = center_h * _CENTER_ASPECT
        unit_w = center_w / _DEPTH_FLEX["center"]
        sizes = [[unit_w * _DEPTH_FLEX.get(c._depth, 0.85), center_h * c.height_ratio()]
                 for c in cards]

        total_w = sum(s[0] for s in sizes) + _CARD_GAP * (len(sizes) - 1)
        if total_w > avail_w and total_w > 0:
            scale = avail_w / total_w
            sizes = [[w * scale, h * scale] for w, h in sizes]
            total_w = avail_w

        # 锚点：把 center 卡中点对齐画布中线；无 center 则整组居中
        depths = [c._depth for c in cards]
        if "center" in depths:
            ci = depths.index("center")
            left_w = sum(sizes[k][0] for k in range(ci)) + _CARD_GAP * ci
            group_left = aw / 2 - (left_w + sizes[ci][0] / 2)
            # 安全夹取：整组不超出左右边距
            group_left = max(_CARDS_MARGIN,
                             min(group_left, aw - _CARDS_MARGIN - total_w))
        else:
            group_left = (aw - total_w) / 2

        x = group_left
        for c, (w, h) in zip(cards, sizes):
            y = (ah - h) / 2
            c.setGeometry(int(round(x)), int(round(y)), int(round(w)), int(round(h)))
            x += w + _CARD_GAP

        # 空状态提示：居中显示在加号卡正上方
        if self._hint is not None and cards:
            add = cards[0]
            hh = self._hint.sizeHint().height()
            hw = min(self._hint.sizeHint().width() + 8, aw)
            self._hint.setGeometry((aw - hw) // 2, max(0, add.y() - hh - 16), hw, hh)

    # 兼容旧调用名（测试/历史代码）
    def _apply_card_heights(self) -> None:
        self._relayout_cards()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._relayout_cards()

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # 背景比标题栏(#0d1020 ≈ rgb13,16,32)略浅、且为蓝紫调而非中性灰；
        # 不再下探到近黑 #08090f（那会比标题栏更深、形成高对比灰带）。
        bg = QLinearGradient(0, 0, w, h)
        bg.setColorAt(0.0, QColor("#161a31"))   # (22,26,49) 略浅
        bg.setColorAt(0.5, QColor("#13162c"))   # (19,22,44) 仍略浅于标题栏
        bg.setColorAt(1.0, QColor("#181230"))   # (24,18,48) 微紫
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
