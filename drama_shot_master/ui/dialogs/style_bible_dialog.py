"""STYLE BIBLE 选择器弹窗（②b 风格圣经）。

由 OverviewPage.styleBibleEditRequested 触发，选定结果写
`project.json.style_bible.ref` + 项目快照 `风格圣经.json`。

结构（研究 §4.1 / spec ②b）：
- 顶部三 tab：「模板」/「自定义」/「AI 生成」——本期只实「模板」实卡，
  另两 tab 占位（后续波次接 RefImageGenerator）。
- 模板 tab 内：分类筛选 真人(real) / 2D / 3D，按 `style_bible.load_styles()`
  渲染风格卡（name_cn + prompt_suffix 摘要）。
- 选中一张卡 → `result_value()` 返回 {"ref": style_id, "category": real|2D|3D}；
  取消 / 未选 → None。

视觉：蓝紫主题（与 CapsuleButton 一致 #4a9eff→#a06cff）；卡片自绘选中态，
Win11 QSS 渐变不稳定故选中描边/底色走自绘，纯色为主。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QWidget,
    QLabel,
    QButtonGroup,
    QPushButton,
    QScrollArea,
    QGridLayout,
    QDialogButtonBox,
    QFrame,
    QSizePolicy,
)

from drama_shot_master.core import style_bible

# 蓝紫主题主色（与 CapsuleButton / 欢迎页一致）
_ACCENT = "#7c5cff"        # 选中描边/底色
_ACCENT_SOFT = "#2a2350"   # 选中卡背景（深蓝紫）
_CARD_BG = "#1f2030"
_CARD_BORDER = "#34354a"

# 分类显示顺序与中文名（真人 real / 2D / 3D）
_CATEGORIES: list[tuple[str, str]] = [
    ("real", "真人"),
    ("2D", "2D"),
    ("3D", "3D"),
]


class _StyleCard(QFrame):
    """单张风格卡：name_cn 标题 + prompt_suffix 摘要；点击切换选中态。"""

    def __init__(self, style: dict, on_click, parent=None):
        super().__init__(parent)
        self.style_id: str = style.get("style_id", "")
        self.category: str = style.get("category", "")
        self._on_click = on_click
        self._selected = False

        self.setObjectName("StyleCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setMinimumSize(180, 96)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(4)

        self.title_label = QLabel(style.get("name_cn") or self.style_id)
        self.title_label.setStyleSheet("color:#e8eaed; font-weight:600; font-size:14px;")
        lay.addWidget(self.title_label)

        suffix = (style.get("prompt_suffix") or "").strip()
        self.summary_label = QLabel(suffix)
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("color:#9aa0a6; font-size:11px;")
        lay.addWidget(self.summary_label)
        lay.addStretch(1)

        self._apply_style()

    def title(self) -> str:
        return self.title_label.text()

    def set_selected(self, on: bool) -> None:
        self._selected = on
        self._apply_style()

    def _apply_style(self) -> None:
        if self._selected:
            self.setStyleSheet(
                f"#StyleCard{{background:{_ACCENT_SOFT};"
                f"border:2px solid {_ACCENT}; border-radius:10px;}}"
            )
        else:
            self.setStyleSheet(
                f"#StyleCard{{background:{_CARD_BG};"
                f"border:1px solid {_CARD_BORDER}; border-radius:10px;}}"
            )

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._on_click(self.style_id)
        super().mousePressEvent(event)


class StyleBibleDialog(QDialog):
    """风格圣经选择器。result_value()->{"ref":id,"category":cat}|None。"""

    _CARDS_PER_ROW = 2

    def __init__(self, styles_path=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("风格圣经")
        self.setMinimumSize(560, 480)

        # 全局风格库（缺失/损坏安全降级为空）
        try:
            data = style_bible.load_styles(styles_path)
            self._all_styles: list[dict] = list(data.get("styles", []))
        except Exception:
            self._all_styles = []

        self._category = "real"          # 当前分类
        self._selected_id: str | None = None
        self._result: dict | None = None
        self._cards: list[_StyleCard] = []

        self._build_ui()
        self._reload_cards()

    # ---- UI 装配 ----
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        title = QLabel("STYLE BIBLE · 风格圣经")
        title.setStyleSheet(f"color:{_ACCENT}; font-weight:700; font-size:16px;")
        root.addWidget(title)

        # 顶部三 tab：模板（实）/ 自定义（占位）/ AI 生成（占位）
        self.tabs = QTabWidget(self)
        self.tabs.addTab(self._build_template_tab(), "模板")
        self.tabs.addTab(self._build_placeholder("自定义风格（后续支持）"), "自定义")
        self.tabs.addTab(self._build_placeholder("AI 生成风格（后续支持）"), "AI 生成")
        root.addWidget(self.tabs, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _build_placeholder(self, text: str) -> QWidget:
        w = QWidget(self)
        lay = QVBoxLayout(w)
        lab = QLabel(text)
        lab.setAlignment(Qt.AlignCenter)
        lab.setStyleSheet("color:#6b7080; font-size:13px;")
        lay.addStretch(1)
        lay.addWidget(lab)
        lay.addStretch(1)
        return w

    def _build_template_tab(self) -> QWidget:
        w = QWidget(self)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(10)

        # 分类筛选条
        cat_row = QHBoxLayout()
        cat_row.setSpacing(8)
        self._cat_group = QButtonGroup(self)
        self._cat_group.setExclusive(True)
        for cat_id, cat_cn in _CATEGORIES:
            b = QPushButton(cat_cn)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setProperty("category_id", cat_id)
            b.setStyleSheet(self._cat_button_qss())
            b.clicked.connect(lambda _=False, c=cat_id: self.set_category(c))
            if cat_id == self._category:
                b.setChecked(True)
            self._cat_group.addButton(b)
            cat_row.addWidget(b)
        cat_row.addStretch(1)
        lay.addLayout(cat_row)

        # 卡片滚动区
        self._cards_host = QWidget(self)
        self._cards_grid = QGridLayout(self._cards_host)
        self._cards_grid.setContentsMargins(0, 0, 0, 0)
        self._cards_grid.setSpacing(10)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self._cards_host)
        lay.addWidget(scroll, 1)
        return w

    @staticmethod
    def _cat_button_qss() -> str:
        return (
            "QPushButton{color:#c4cad6; background:#26273a;"
            "border:1px solid #34354a; border-radius:14px; padding:5px 16px;}"
            f"QPushButton:checked{{color:#fff; background:{_ACCENT};"
            f"border:1px solid {_ACCENT};}}"
        )

    # ---- 分类/卡片渲染 ----
    def _styles_for_category(self, category: str) -> list[dict]:
        return [s for s in self._all_styles if s.get("category") == category]

    def _reload_cards(self) -> None:
        # 清空旧卡
        while self._cards_grid.count():
            item = self._cards_grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._cards = []

        styles = self._styles_for_category(self._category)
        for idx, st in enumerate(styles):
            card = _StyleCard(st, self.select_style, self._cards_host)
            if st.get("style_id") == self._selected_id:
                card.set_selected(True)
            r, c = divmod(idx, self._CARDS_PER_ROW)
            self._cards_grid.addWidget(card, r, c)
            self._cards.append(card)

    def set_category(self, category: str) -> None:
        """切换分类筛选并重渲染卡片。"""
        self._category = category
        # 同步分类按钮选中态（程序化调用时）
        for b in self._cat_group.buttons():
            b.setChecked(b.property("category_id") == category)
        self._reload_cards()

    def select_style(self, style_id: str) -> None:
        """选中某张风格卡（同分类内单选高亮）。"""
        self._selected_id = style_id
        for card in self._cards:
            card.set_selected(card.style_id == style_id)

    # ---- 测试/调用方查询 ----
    def visible_style_ids(self) -> list[str]:
        return [c.style_id for c in self._cards]

    def visible_card_titles(self) -> list[str]:
        return [c.title() for c in self._cards]

    def result_value(self) -> dict | None:
        return self._result

    # ---- accept/reject ----
    def accept(self) -> None:  # noqa: D102
        if self._selected_id:
            st = next(
                (s for s in self._all_styles if s.get("style_id") == self._selected_id),
                None,
            )
            cat = st.get("category") if st else self._category
            self._result = {"ref": self._selected_id, "category": cat}
        else:
            self._result = None
        super().accept()

    def reject(self) -> None:  # noqa: D102
        self._result = None
        super().reject()
