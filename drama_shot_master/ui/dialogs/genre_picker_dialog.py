"""题材选择器弹窗（②b · R4）。

用 genre_templates.list_genres() 渲染 6 张题材卡（短剧/单集短篇/商业广告/
vlog/MV/口播剧），每张卡显示 display_name + identity.one_liner。

交互（0xsline 叠加规则，研究 §3）：
- 选 1 个主题材（定基调与 params）；
- 叠加若干副题材（副只覆盖 satisfaction_weights）；
- 主 + 副总数 ≤ STACK_MAX（默认 3）；主题材不可同时作副题材；
- result_value() -> {"genre": 主id, "sub": [副id...]} | None（取消为 None）。

视觉：蓝紫主题、纯色卡（QSS 渐变在 Win11 不稳定 → 自绘纯色 + 边框态切换）。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QFrame,
    QDialogButtonBox,
    QWidget,
)

from drama_shot_master.core.genre_templates import (
    list_genres,
    load_genre,
    STACK_MAX,
)

# 蓝紫主题纯色（不用 QSS 渐变；Win11 渲染不稳定 → 纯色 + 边框态）
_CARD_BG = "#241c3a"          # 卡底（深蓝紫）
_CARD_BG_HOVER = "#2e2450"
_PRIMARY_BG = "#4b2fb0"       # 主题材选中（蓝紫高亮）
_PRIMARY_BORDER = "#8b6cff"
_SUB_BG = "#33285c"           # 副题材选中
_SUB_BORDER = "#6c5ce7"
_IDLE_BORDER = "#3a3057"
_TITLE_FG = "#f2efff"
_DESC_FG = "#b9b0d8"


class GenreCard(QFrame):
    """单张题材卡（纯色自绘）。点击主区选主，点击右下角徽标切换副。

    对外属性（供测试/容器读取）：
    - genre_id / title_text / one_liner_text
    - is_primary / is_sub（状态）
    信号：
    - primaryRequested(genre_id)
    - subToggleRequested(genre_id)
    """

    primaryRequested = Signal(str)
    subToggleRequested = Signal(str)

    def __init__(self, genre_id: str, display_name: str, one_liner: str, parent=None):
        super().__init__(parent)
        self.genre_id = genre_id
        self.title_text = display_name
        self.one_liner_text = one_liner
        self.is_primary = False
        self.is_sub = False

        self.setObjectName("genreCard")
        self.setFixedSize(220, 132)
        self.setFrameShape(QFrame.NoFrame)
        self.setCursor(Qt.PointingHandCursor)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(6)

        self._title = QLabel(display_name)
        self._title.setStyleSheet(
            f"color:{_TITLE_FG}; font-size:15px; font-weight:600;"
        )
        lay.addWidget(self._title)

        self._desc = QLabel(one_liner)
        self._desc.setWordWrap(True)
        self._desc.setStyleSheet(f"color:{_DESC_FG}; font-size:12px;")
        self._desc.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        lay.addWidget(self._desc, 1)

        # 状态徽标（主/副）
        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 0, 0, 0)
        badge_row.addStretch(1)
        self._badge = QLabel("")
        self._badge.setStyleSheet(
            f"color:{_TITLE_FG}; font-size:11px; font-weight:600;"
        )
        badge_row.addWidget(self._badge)
        lay.addLayout(badge_row)

        self._refresh_style()

    # —— 交互 ——
    def mousePressEvent(self, event):  # noqa: N802 (Qt 命名)
        if event.button() == Qt.LeftButton:
            # 右下角区域 → 切换副题材；其余 → 设为主题材
            if event.position().y() > self.height() - 40 \
                    and event.position().x() > self.width() - 90:
                self.subToggleRequested.emit(self.genre_id)
            else:
                self.primaryRequested.emit(self.genre_id)
        super().mousePressEvent(event)

    def set_state(self, *, primary: bool, sub: bool) -> None:
        self.is_primary = primary
        self.is_sub = sub
        self._refresh_style()

    def _refresh_style(self) -> None:
        if self.is_primary:
            bg, border, badge = _PRIMARY_BG, _PRIMARY_BORDER, "主题材"
        elif self.is_sub:
            bg, border, badge = _SUB_BG, _SUB_BORDER, "副 +"
        else:
            bg, border, badge = _CARD_BG, _IDLE_BORDER, ""
        self.setStyleSheet(
            f"#genreCard{{background:{bg}; border:2px solid {border};"
            f" border-radius:12px;}}"
        )
        self._badge.setText(badge)


class GenrePickerDialog(QDialog):
    """题材选择器（主 + 副 ≤3）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择题材")
        self.setMinimumWidth(760)
        self.setStyleSheet("QDialog{background:#1a1430;}")

        self._primary: str | None = None
        self._subs: list[str] = []
        self._result: dict | None = None
        self.cards: list[GenreCard] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(14)

        title = QLabel("选择题材（主题材定基调，副题材叠加爽点，主+副 ≤ "
                       f"{STACK_MAX}）")
        title.setStyleSheet(f"color:{_TITLE_FG}; font-size:16px; font-weight:600;")
        root.addWidget(title)

        hint = QLabel("点击卡片选为主题材；点击右下角「副 +」叠加副题材。")
        hint.setStyleSheet(f"color:{_DESC_FG}; font-size:12px;")
        root.addWidget(hint)

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        root.addWidget(grid_host)

        for idx, genre_id in enumerate(list_genres()):
            data = load_genre(genre_id)
            display_name = data.get("display_name", genre_id)
            one_liner = (data.get("identity") or {}).get("one_liner", "")
            card = GenreCard(genre_id, display_name, one_liner)
            card.primaryRequested.connect(self.set_primary)
            card.subToggleRequested.connect(self.toggle_sub)
            grid.addWidget(card, idx // 3, idx % 3)
            self.cards.append(card)

        self._status = QLabel("")
        self._status.setStyleSheet(f"color:{_DESC_FG}; font-size:12px;")
        root.addWidget(self._status)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        self._refresh_cards()

    # —— 选择逻辑 ——
    def set_primary(self, genre_id: str) -> None:
        """设为主题材。若该 id 原为副题材，则从副列表移出。"""
        if genre_id not in {c.genre_id for c in self.cards}:
            return
        self._primary = genre_id
        if genre_id in self._subs:
            self._subs.remove(genre_id)
        self._refresh_cards()

    def toggle_sub(self, genre_id: str) -> bool:
        """切换副题材。返回操作后该 id 是否处于「副选中」态。

        约束（0xsline 叠加）：
        - 主题材不可同时作副题材 → 拒绝（False）；
        - 主 + 副总数 ≤ STACK_MAX；新增会超限 → 拒绝（False）。
        """
        if genre_id not in {c.genre_id for c in self.cards}:
            return False
        if genre_id == self._primary:
            return False
        if genre_id in self._subs:
            self._subs.remove(genre_id)
            self._refresh_cards()
            return False
        # 主占 1 名额（若已选主）；总数上限 STACK_MAX
        used = (1 if self._primary else 0) + len(self._subs)
        if used >= STACK_MAX:
            self._refresh_cards()
            return False
        self._subs.append(genre_id)
        self._refresh_cards()
        return True

    def _refresh_cards(self) -> None:
        for card in self.cards:
            card.set_state(
                primary=(card.genre_id == self._primary),
                sub=(card.genre_id in self._subs),
            )
        used = (1 if self._primary else 0) + len(self._subs)
        primary_txt = self._primary or "未选"
        self._status.setText(
            f"主题材：{primary_txt}　副题材：{len(self._subs)} 个"
            f"　（已用 {used}/{STACK_MAX}）"
        )

    # —— 结果 ——
    def accept(self) -> None:  # noqa: N802
        self._result = {"genre": self._primary, "sub": list(self._subs)}
        super().accept()

    def reject(self) -> None:  # noqa: N802
        self._result = None
        super().reject()

    def result_value(self) -> dict | None:
        """{"genre": 主id, "sub": [副id...]} | None（取消/未确认为 None）。"""
        return self._result
