# drama_shot_master/ui/pages/overview_page.py
"""项目「概览」仪表盘页（compass 数据驱动）。

视觉规格见 docs/explorer/project-overview-dashboard-confirm.html（v3）：
  · STYLE BIBLE 卡（紫色左边框）：显示当前风格圣经名/描述，编辑按钮。
  · next-action banner（蓝色）：当前进行中阶段的 next_action 文案。
  · 5 阶段横向流水线卡：剧本创作 / 资源库 / 分镜板 / 视频生成 / 视频后期。

阶段 ↔ compass stage 对齐：
  剧本创作=screenwriter / 资源库=assets / 分镜板=storyboard /
  视频生成=production / 视频后期=production（项目级，配音+配乐两行）。

QSS 渐变在 Win11 下不稳 → 关键层级用纯色 + 细边框 + 描边表达，
渐变背景/光晕一律走 QPainter 自绘（paintEvent），自绘控件父级保持
background:transparent 避免灰底盖住自绘层。数据全程 getattr 兜底不崩。
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QBrush, QLinearGradient
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
)

from drama_shot_master.core import style_bible as _style_bible

# 主题 token（navy / 蓝 #4a9eff / 紫，非绿）
_PANEL = "#202234"
_BORDER = "#2c2f48"
_FG = "#e8eaed"
_FG2 = "#c4c8d4"
_MUTED = "#9aa0a6"
_FAINT = "#5a6076"
_BLUE = "#4a9eff"
_BLUE_DIM = "#2f5e96"
_PERIW = "#8b7fd9"
_DONE = "#4ec98f"
_LOCKED = "#4a4f63"

# 5 阶段卡定义：(显示名, stage_key, 副标签)
# 视频生成 / 视频后期 共用 compass production stage（两张卡同 key）。
_STAGE_DEFS = [
    ("剧本创作", "screenwriter", ""),
    ("资源库", "assets", ""),
    ("分镜板", "storyboard", "出图+拆拼裁"),
    ("视频生成", "production", ""),
    ("视频后期", "production", "配音·配乐"),
]

# compass state → 卡片 state class（done/cur/locked）+ 角标字形
_STATE_CLASS = {
    "completed": "done",
    "in_progress": "cur",
    "pending": "locked",
}
_STATE_BADGE = {"done": "✓", "cur": "●", "locked": "🔒"}


class StageCard(QWidget):
    """单张阶段卡：纯色面板 + 细边框，state class 决定边框/角标。

    点击发 activated(stage_key)。视频后期卡（is_postproduction）显
    配音 / 配乐（项目级）两行而非单个大数字。
    """

    activated = Signal(str)

    def __init__(self, title: str, stage_key: str, sub: str = "",
                 is_postproduction: bool = False,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.stage_key = stage_key
        self._title = title
        self._sub = sub
        self._is_post = is_postproduction
        self._state_class = "locked"
        self.setObjectName("StageCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(108)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._build_ui()
        self._apply_style()

    # ---- 构建 --------------------------------------------------------
    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(5)

        # 头部：阶段名 + state 角标
        hd = QHBoxLayout()
        hd.setSpacing(6)
        self._name_lbl = QLabel(self._title)
        self._name_lbl.setObjectName("StageCardName")
        hd.addWidget(self._name_lbl)
        hd.addStretch(1)
        self._badge_lbl = QLabel("🔒")
        self._badge_lbl.setObjectName("StageCardBadge")
        hd.addWidget(self._badge_lbl)
        lay.addLayout(hd)

        if self._is_post:
            # 视频后期：配音 / 配乐（项目级）两行
            self._post_dub = QLabel("配音  0/0")
            self._post_dub.setObjectName("StageCardPostLine")
            self._post_mus = QLabel("配乐  项目级·0/1")
            self._post_mus.setObjectName("StageCardPostMusic")
            lay.addWidget(self._post_dub)
            lay.addWidget(self._post_mus)
            self._big_lbl = None
            self._meta_lbl = None
        else:
            self._big_lbl = QLabel("0/0")
            self._big_lbl.setObjectName("StageCardBig")
            lay.addWidget(self._big_lbl)
            self._meta_lbl = QLabel(self._sub or "")
            self._meta_lbl.setObjectName("StageCardMeta")
            self._meta_lbl.setWordWrap(True)
            lay.addWidget(self._meta_lbl)

        lay.addStretch(1)

    # ---- 状态/数据 ---------------------------------------------------
    def set_state(self, compass_state: str) -> None:
        """按 compass state（completed/in_progress/pending）设卡片样式。"""
        self._state_class = _STATE_CLASS.get(compass_state, "locked")
        self._badge_lbl.setText(_STATE_BADGE.get(self._state_class, "🔒"))
        self._apply_style()

    def state_class(self) -> str:
        """done / cur / locked。"""
        return self._state_class

    def set_progress(self, done: int, total: int, meta: str = "") -> None:
        """设进度数字与副文案（非后期卡）。"""
        if self._big_lbl is not None:
            self._big_lbl.setText(f"{done}/{total}")
        if self._meta_lbl is not None and meta:
            self._meta_lbl.setText(meta)

    def set_post_progress(self, dub_done: int, dub_total: int,
                          music_done: int, music_total: int) -> None:
        """设视频后期卡的 配音 / 配乐（项目级）两行进度。"""
        if self._is_post:
            self._post_dub.setText(f"配音  {dub_done}/{dub_total}")
            self._post_mus.setText(f"配乐  项目级·{music_done}/{music_total}")

    # ---- 样式 --------------------------------------------------------
    def _apply_style(self) -> None:
        # cur：蓝边高亮；done：绿角标；locked：半透明灰
        if self._state_class == "cur":
            border = _BLUE
        elif self._state_class == "done":
            border = "#2c5a44"
        else:
            border = _BORDER
        badge_color = {"done": _DONE, "cur": _BLUE, "locked": _FAINT}[
            self._state_class]
        opacity = "" if self._state_class != "locked" else "color:%s;" % _LOCKED
        self.setStyleSheet(
            "#StageCard{background:%s;border:1px solid %s;border-radius:11px;}"
            "#StageCardName{font-size:12px;font-weight:600;color:%s;}"
            "#StageCardBadge{font-size:11px;color:%s;}"
            "#StageCardBig{font-size:24px;font-weight:750;color:%s;}"
            "#StageCardMeta{font-size:9px;color:%s;}"
            "#StageCardPostLine{font-size:11px;color:%s;}"
            "#StageCardPostMusic{font-size:11px;color:%s;}"
            % (_PANEL, border, _FG2, badge_color,
               _FG if self._state_class != "locked" else _LOCKED,
               _MUTED, _FG2, _PERIW)
        )

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.activated.emit(self.stage_key)
        super().mousePressEvent(event)


class OverviewPage(QWidget):
    """项目概览仪表盘。set_manifest(manifest) 后渲染全部区块。

    对外信号：
      styleBibleEditRequested — 点 STYLE BIBLE 卡「编辑」。
      stageActivated(stage_key) — 点某阶段卡。
    """

    styleBibleEditRequested = Signal()
    stageActivated = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("OverviewPage")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._manifest = None
        self._stage_cards: list[StageCard] = []
        self._build_ui()

    # ---- 构建 --------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 15, 18, 18)
        root.setSpacing(12)

        root.addWidget(self._make_bible_card())
        root.addWidget(self._make_next_banner())
        root.addLayout(self._make_flow_row())
        root.addStretch(1)

        self.setStyleSheet(
            "#OverviewPage{background:#1e1f22;}"
        )

    def _make_bible_card(self) -> QWidget:
        card = QWidget()
        card.setObjectName("BibleCard")
        card.setAttribute(Qt.WA_StyledBackground, True)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(15, 12, 15, 12)
        lay.setSpacing(13)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)
        title = QLabel("全片风格圣经 · STYLE BIBLE")
        title.setObjectName("BibleTitle")
        text_col.addWidget(title)
        self._bible_desc = QLabel("未设定")
        self._bible_desc.setObjectName("BibleDesc")
        self._bible_desc.setWordWrap(True)
        text_col.addWidget(self._bible_desc)
        lay.addLayout(text_col, 1)

        self._edit_btn = QPushButton("编辑")
        self._edit_btn.setObjectName("BibleEditBtn")
        self._edit_btn.setCursor(Qt.PointingHandCursor)
        self._edit_btn.clicked.connect(self.styleBibleEditRequested)
        lay.addWidget(self._edit_btn, 0, Qt.AlignVCenter)

        card.setStyleSheet(
            "#BibleCard{background:%s;border:1px solid %s;"
            "border-left:3px solid %s;border-radius:11px;}"
            "#BibleTitle{font-size:12px;font-weight:650;color:%s;}"
            "#BibleDesc{font-size:10px;color:%s;}"
            "#BibleEditBtn{font-size:11px;color:%s;border:1px solid %s;"
            "border-radius:7px;padding:5px 12px;background:rgba(74,158,255,0.06);}"
            % (_PANEL, _BORDER, _PERIW, _FG, _MUTED, _BLUE, _BLUE_DIM)
        )
        return card

    def _make_next_banner(self) -> QWidget:
        banner = QWidget()
        banner.setObjectName("NextBanner")
        banner.setAttribute(Qt.WA_StyledBackground, True)
        lay = QHBoxLayout(banner)
        lay.setContentsMargins(13, 8, 13, 8)
        lay.setSpacing(10)
        self._next_lbl = QLabel("")
        self._next_lbl.setObjectName("NextBannerText")
        self._next_lbl.setWordWrap(True)
        lay.addWidget(self._next_lbl, 1)

        banner.setStyleSheet(
            "#NextBanner{background:rgba(74,158,255,0.07);"
            "border:1px solid #243a5a;border-radius:9px;}"
            "#NextBannerText{font-size:11px;color:#bcd4f5;}"
        )
        return banner

    def _make_flow_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        self._stage_cards = []
        for i, (title, key, sub) in enumerate(_STAGE_DEFS):
            is_post = (title == "视频后期")
            card = StageCard(title, key, sub, is_postproduction=is_post)
            card.activated.connect(self.stageActivated)
            self._stage_cards.append(card)
            row.addWidget(card, 1)
            if i < len(_STAGE_DEFS) - 1:
                arrow = QLabel("›")
                arrow.setObjectName("FlowArrow")
                arrow.setAlignment(Qt.AlignCenter)
                arrow.setStyleSheet("color:%s;font-size:14px;" % _FAINT)
                row.addWidget(arrow, 0)
        return row

    # ---- 公开 API ----------------------------------------------------
    def set_manifest(self, manifest) -> None:
        """渲染：STYLE BIBLE 卡 / next-action banner / 5 阶段卡。

        manifest 可为 None 或缺字段，全程 getattr 兜底不崩。
        """
        self._manifest = manifest
        self._render_bible(manifest)
        self._render_next_action(manifest)
        self._render_stages(manifest)

    def stage_cards(self) -> list[StageCard]:
        return list(self._stage_cards)

    def style_bible_text(self) -> str:
        return self._bible_desc.text()

    def next_action_text(self) -> str:
        return self._next_lbl.text()

    # ---- 渲染逻辑 ----------------------------------------------------
    def _render_bible(self, manifest) -> None:
        bible = getattr(manifest, "style_bible", None) or {}
        ref = bible.get("ref") if isinstance(bible, dict) else None
        if not ref:
            self._bible_desc.setText("未设定")
            return
        style = None
        try:
            style = _style_bible.get_style(ref)
        except Exception:
            style = None
        if not style:
            # ref 指向未知 id：仍显示 id 兜底，不崩
            self._bible_desc.setText("未设定（%s）" % ref)
            return
        name = style.get("name_cn") or ref
        suffix = style.get("prompt_suffix") or ""
        if suffix:
            self._bible_desc.setText("%s（%s）：%s" % (name, ref, suffix))
        else:
            self._bible_desc.setText("%s（%s）" % (name, ref))

    def _render_next_action(self, manifest) -> None:
        pipeline = getattr(manifest, "pipeline", None) or {}
        text = ""
        # 优先取进行中阶段的 next_action
        for key in ("screenwriter", "assets", "storyboard", "production"):
            st = pipeline.get(key) if isinstance(pipeline, dict) else None
            state = getattr(st, "state", None)
            action = getattr(st, "next_action", "") or ""
            if state == "in_progress" and action:
                text = "下一步 · %s" % action
                break
        if not text:
            # 退而求其次：任意 next_action 非空
            for key in ("screenwriter", "assets", "storyboard", "production"):
                st = pipeline.get(key) if isinstance(pipeline, dict) else None
                action = getattr(st, "next_action", "") or ""
                if action:
                    text = "下一步 · %s" % action
                    break
        self._next_lbl.setText(text)

    def _render_stages(self, manifest) -> None:
        pipeline = getattr(manifest, "pipeline", None) or {}
        episodes = getattr(manifest, "episodes", None) or {}
        params = getattr(manifest, "params", None) or {}
        ep_total = self._episode_total(episodes, params)

        for card in self._stage_cards:
            st = pipeline.get(card.stage_key) if isinstance(pipeline, dict) else None
            state = getattr(st, "state", "pending") or "pending"
            card.set_state(state)
            self._fill_stage_progress(card, manifest, episodes, params, ep_total)

    def _fill_stage_progress(self, card, manifest, episodes, params, ep_total) -> None:
        """逐卡填进度数字（缺则 0/总），数据缺失兜底。"""
        key = card.stage_key
        title = card._title
        try:
            if title == "剧本创作":
                done = sum(1 for e in episodes.values()
                           if getattr(e, "script", ""))
                card.set_progress(done, ep_total or len(episodes) or 0,
                                  "编剧 · 逐集")
            elif title == "资源库":
                # 参考图总数难直接取 → 0/0 兜底
                card.set_progress(0, 0, "角色 / 场景 / 道具 参考图")
            elif title == "分镜板":
                shots = sum(len(getattr(e, "shots_done", []) or [])
                            for e in episodes.values())
                card.set_progress(shots, 0, "出图 · 已出图")
            elif title == "视频生成":
                vdone = sum(1 for e in episodes.values()
                            if getattr(e, "video_done", False))
                card.set_progress(vdone, ep_total or len(episodes) or 0,
                                  "生视频 · 按集")
            elif title == "视频后期":
                vdone = sum(1 for e in episodes.values()
                            if getattr(e, "video_done", False))
                card.set_post_progress(0, ep_total or len(episodes) or 0,
                                       0, 1)
        except Exception:
            # 任何字段异常都不让一张卡拖垮整页
            pass

    @staticmethod
    def _episode_total(episodes, params) -> int:
        """集数总量：优先 params.episode_count，否则 len(episodes)。"""
        for k in ("episode_count", "episodes", "ep_count"):
            v = params.get(k) if isinstance(params, dict) else None
            try:
                if v:
                    return int(v)
            except (TypeError, ValueError):
                continue
        try:
            return len(episodes)
        except TypeError:
            return 0

    # ---- 背景自绘（QSS 渐变在 Win11 不稳，走 QPainter）----------------
    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        bg = QLinearGradient(0, 0, 0, self.height())
        bg.setColorAt(0.0, QColor("#1e1f22"))
        bg.setColorAt(1.0, QColor("#1a1b24"))
        p.fillRect(self.rect(), QBrush(bg))
        p.end()
        super().paintEvent(event)
