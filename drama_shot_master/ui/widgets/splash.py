# drama_shot_master/ui/widgets/splash.py
"""启动加载窗口（B 版分阶段工作区 · 蓝紫主题）。

无边框 QWidget，渐变背景用 QPainter 自绘（Win11 QSS 渐变不渲染，须自画/纯色）。
结构：品牌区(真实图标+标题+版本) + 分阶段清单(3 步) + 进度条 + 提示行 + 作者(商务条件显示)。
对外 API：set_stage(idx, state)/set_progress(v)/set_credits(author, business)/set_tip(text)。
mockup 参考：docs/explorer/loading-splash-confirm.html。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRect, QRectF, QPointF, QTimer
from PySide6.QtGui import (
    QPainter, QColor, QLinearGradient, QConicalGradient, QRadialGradient,
    QBrush, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy,
)

from drama_shot_master.ui.theme import _find_app_icon_path

# 取自 tokens_dark / loading-splash-confirm.html B 版蓝紫 token
_NAVY = "#0d1020"
_INDIGO = "#1e1e3a"
_INDIGO2 = "#2a2a4a"
_BLUE = "#4a9eff"
_PERIW = "#8b7fd9"
_MAUVE = "#a78bfa"
_MINT = "#7fe0c8"
_TXT = "#e8eaed"
_DIM = "#9aa0a6"
_SUB = "#5a6a8a"
_FAINT = "#46506e"
_DONE = "#4ec98f"

_BRAND_TITLE = "糯米AI分镜影视创作台"
_VERSION_LINE = "NUOMI AI · STORYBOARD STUDIO   v0.9"

# 步状态 → (圆点字符, 标签色)
_STAGE_GLYPH = {"done": "✓", "active": "⟳", "pending": "○"}

_DEFAULT_STAGES = ("加载配置 / 风格圣经", "索引项目资源", "准备工作区")


class _StageRow(QWidget):
    """单步清单行：圆点图标 + 标签 + 迷你进度条。状态 done/active/pending。"""

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._state = "pending"
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        self._ic = QLabel()
        self._ic.setObjectName("SplashStageIcon")
        self._ic.setFixedSize(18, 18)
        self._ic.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._ic)

        self._lab = QLabel(text)
        self._lab.setObjectName("SplashStageLabel")
        lay.addWidget(self._lab)
        lay.addStretch(1)

        self.set_state("pending")

    def set_state(self, state: str) -> None:
        self._state = state
        glyph = _STAGE_GLYPH.get(state, "○")
        self._ic.setText(glyph)
        if state == "done":
            ic_css = (f"color:#06140b;background:{_DONE};"
                      f"border:1.5px solid {_DONE};border-radius:9px;")
            lab_css = f"color:{_TXT};"
        elif state == "active":
            ic_css = (f"color:{_BLUE};background:transparent;"
                      f"border:1.5px solid {_BLUE};border-radius:9px;")
            lab_css = f"color:#dbe2ff;font-weight:600;"
        else:
            ic_css = (f"color:{_FAINT};background:transparent;"
                      f"border:1.5px solid {_INDIGO2};border-radius:9px;")
            lab_css = f"color:{_DIM};"
        self._ic.setStyleSheet(f"font-size:10px;{ic_css}")
        self._lab.setStyleSheet(f"font-size:12px;{lab_css}")

    def state(self) -> str:
        return self._state


class SplashScreen(QWidget):
    """启动加载窗口。

    无边框 + 透明背景属性，渐变 / 光晕全部 QPainter 自绘（Win11 QSS 渐变坑）。
    外部启动序列通过 set_stage/set_progress/set_credits/set_tip 驱动。
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("SplashScreen")
        # 无边框 + 置顶 + 透明角（圆角自绘）
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.SplashScreen | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        # 自绘背景：不启用 styled background，避免 QSS 渐变占位
        self.setFixedSize(480, 408)

        self._progress = 0.0
        self._stage_rows: list[_StageRow] = []
        self._stages = list(_DEFAULT_STAGES)

        # 环形 loading 动画：QTimer 自增角度 → update() 触发 paintEvent 重绘旋转弧。
        # （HTML mockup 的 .mark .ring 用 CSS spin 2.4s linear，这里用 ~60fps 定时器复刻。）
        self._ring_angle = 0.0
        self._spin_timer = QTimer(self)
        self._spin_timer.setInterval(16)            # ≈60fps
        self._spin_timer.timeout.connect(self._advance_spin)
        self._spin_timer.start()

        self._build_ui()

    def _advance_spin(self) -> None:
        """每帧推进环角度并请求重绘（驱动品牌图标外圈旋转弧）。"""
        self._ring_angle = (self._ring_angle + 6.0) % 360.0
        self.update()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(0)

        # 顶部 LOADING pill 行
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        pill = QLabel("● LOADING")
        pill.setObjectName("SplashPill")
        pill.setStyleSheet(
            f"color:{_BLUE};font-size:10px;font-weight:600;letter-spacing:1.2px;"
            f"border:1px solid #294a78;background:rgba(74,158,255,0.10);"
            f"border-radius:10px;padding:2px 10px;"
        )
        top.addWidget(pill)
        top.addStretch(1)
        root.addLayout(top)

        root.addStretch(1)

        # 品牌区
        brand = QVBoxLayout()
        brand.setSpacing(8)
        brand.setAlignment(Qt.AlignHCenter)

        self._icon_lbl = QLabel()
        self._icon_lbl.setAlignment(Qt.AlignCenter)
        self._icon_lbl.setFixedSize(72, 72)
        self._load_icon()
        brand.addWidget(self._icon_lbl, 0, Qt.AlignHCenter)

        self._title_lbl = QLabel(_BRAND_TITLE)
        self._title_lbl.setObjectName("SplashTitle")
        self._title_lbl.setAlignment(Qt.AlignCenter)
        self._title_lbl.setStyleSheet(
            f"color:{_TXT};font-size:19px;font-weight:750;letter-spacing:0.5px;"
        )
        brand.addWidget(self._title_lbl)

        self._version_lbl = QLabel(_VERSION_LINE)
        self._version_lbl.setAlignment(Qt.AlignCenter)
        self._version_lbl.setStyleSheet(
            f"color:{_SUB};font-size:10px;letter-spacing:2px;"
        )
        brand.addWidget(self._version_lbl)
        root.addLayout(brand)

        # 分阶段清单
        stages_box = QVBoxLayout()
        stages_box.setSpacing(9)
        stages_box.setContentsMargins(75, 12, 75, 0)
        for txt in self._stages:
            row = _StageRow(txt)
            self._stage_rows.append(row)
            stages_box.addWidget(row)
        root.addLayout(stages_box)

        root.addStretch(1)

        # 底部：提示 + 进度条 + 状态/作者
        self._tip_label = QLabel("💡 提示：分镜可按编号一键回填 local_prompt")
        self._tip_label.setObjectName("SplashTip")
        self._tip_label.setStyleSheet(f"color:{_FAINT};font-size:11px;")
        root.addWidget(self._tip_label)
        root.addSpacing(6)

        # 进度条占位（自绘条放在 paintEvent；这里留一个 3px 高度占位）
        self._bar_holder = QWidget()
        self._bar_holder.setFixedHeight(3)
        self._bar_holder.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        root.addWidget(self._bar_holder)
        root.addSpacing(7)

        # 状态行 + 作者/商务
        bl = QHBoxLayout()
        bl.setContentsMargins(0, 0, 0, 0)
        self._status_label = QLabel("")
        self._status_label.setObjectName("SplashStatus")
        self._status_label.setStyleSheet(f"color:{_DIM};font-size:11px;")
        bl.addWidget(self._status_label)
        bl.addStretch(1)

        credits = QVBoxLayout()
        credits.setSpacing(1)
        credits.setAlignment(Qt.AlignRight)
        self._author_label = QLabel("作者 · 二进制糯米")
        self._author_label.setObjectName("SplashAuthor")
        self._author_label.setAlignment(Qt.AlignRight)
        self._author_label.setStyleSheet(f"color:{_FAINT};font-size:10px;")
        credits.addWidget(self._author_label)
        self._business_label = QLabel("")
        self._business_label.setObjectName("SplashBusiness")
        self._business_label.setAlignment(Qt.AlignRight)
        self._business_label.setStyleSheet(f"color:{_SUB};font-size:10px;")
        self._business_label.setVisible(False)
        credits.addWidget(self._business_label)
        bl.addLayout(credits)
        root.addLayout(bl)

        self._author = "二进制糯米"
        self._business = ""
        self._update_status()

    def _load_icon(self) -> None:
        p = _find_app_icon_path()
        if p is not None:
            pix = QPixmap(str(p))
            if not pix.isNull():
                # HiDPI 防糊：按屏幕 devicePixelRatio 渲染到物理像素，再回设逻辑 DPR，
                # 让 Qt 以 1/dpr 缩放显示——避免在 2x 屏上把 62px 逻辑图拉伸成模糊块。
                dpr = self.devicePixelRatioF() or 1.0
                target = 62
                pix = pix.scaled(
                    int(target * dpr), int(target * dpr),
                    Qt.KeepAspectRatio, Qt.SmoothTransformation,
                )
                pix.setDevicePixelRatio(dpr)
                self._icon_lbl.setPixmap(pix)
                return
        # 无图标降级：纯色占位
        self._icon_lbl.setStyleSheet(
            f"background:{_INDIGO};border-radius:15px;"
        )

    # --------------------------------------------------------------- public API
    def brand_title(self) -> str:
        return self._title_lbl.text()

    def set_stage(self, idx: int, state: str) -> None:
        """更新第 idx 步状态：done / active / pending。越界静默忽略。"""
        if 0 <= idx < len(self._stage_rows):
            self._stage_rows[idx].set_state(state)
            self._update_status()

    def stage_state(self, idx: int) -> str:
        if 0 <= idx < len(self._stage_rows):
            return self._stage_rows[idx].state()
        return ""

    def set_progress(self, value: float) -> None:
        """设置总进度 [0,1]，越界夹取。"""
        self._progress = max(0.0, min(1.0, float(value)))
        self.update()

    def progress(self) -> float:
        return self._progress

    def set_credits(self, author: str, business: str = "") -> None:
        """作者必显；商务字段填了显示 / 空则隐藏。"""
        self._author = author or ""
        self._business = business or ""
        self._author_label.setText(f"作者 · {self._author}")
        if self._business.strip():
            self._business_label.setText(f"商务 · {self._business}")
            self._business_label.setVisible(True)
        else:
            self._business_label.setText("")
            self._business_label.setVisible(False)

    def author(self) -> str:
        return self._author

    def set_tip(self, text: str) -> None:
        self._tip_label.setText(text)

    # ------------------------------------------------------------------ helpers
    def _update_status(self) -> None:
        """根据当前步状态刷新「n / 总数 · 当前步名」状态行。"""
        total = len(self._stage_rows)
        done = sum(1 for r in self._stage_rows if r.state() == "done")
        # 当前活跃步（优先 active，否则首个 pending）
        cur_idx = None
        for i, r in enumerate(self._stage_rows):
            if r.state() == "active":
                cur_idx = i
                break
        if cur_idx is None:
            for i, r in enumerate(self._stage_rows):
                if r.state() == "pending":
                    cur_idx = i
                    break
        n = done + (1 if cur_idx is not None else 0)
        n = min(n, total)
        cur_name = self._stages[cur_idx] if cur_idx is not None else "完成"
        self._status_label.setText(f"{n} / {total} · {cur_name}")

    # ------------------------------------------------------------------ paint
    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        rect = QRect(0, 0, w, h)
        radius = 16

        # 圆角裁剪卡片
        from PySide6.QtGui import QPainterPath
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, radius, radius)
        p.setClipPath(path)

        # 底色 navy 渐变
        bg = QLinearGradient(0, 0, w, h)
        bg.setColorAt(0.0, QColor(_NAVY))
        bg.setColorAt(0.5, QColor("#13132a"))
        bg.setColorAt(1.0, QColor("#181230"))
        p.fillRect(rect, QBrush(bg))

        # 蓝/紫/淡紫光晕（自绘 radial，替代 CSS blur）
        self._paint_glow(p, -70, -90, 340, QColor(74, 158, 255, 100))
        self._paint_glow(p, w - 220, h - 200, 300, QColor(139, 127, 217, 105))
        self._paint_glow(p, w - 150, -40, 180, QColor(167, 139, 250, 46))

        # 暗角
        vig = QRadialGradient(w / 2, h / 2, max(w, h) * 0.62)
        vig.setColorAt(0.42, QColor(0, 0, 0, 0))
        vig.setColorAt(1.0, QColor(0, 0, 0, 150))
        p.fillRect(rect, QBrush(vig))

        # 边框
        p.setClipping(False)
        from PySide6.QtGui import QPen
        pen = QPen(QColor(_INDIGO))
        pen.setWidth(1)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(0, 0, w - 1, h - 1, radius, radius)

        # 品牌图标外圈旋转弧（环形 loading 动画，QTimer 驱动 self._ring_angle）
        self._paint_spinner_ring(p)

        # 主进度条（底部 holder 位置自绘）
        self._paint_progress_bar(p)

        p.end()

    def _paint_spinner_ring(self, p: QPainter) -> None:
        """绕品牌图标画一段旋转的渐隐弧（复刻 mockup .mark .ring 的 spin 动画）。"""
        lbl = getattr(self, "_icon_lbl", None)
        if lbl is None:
            return
        top_left = lbl.mapTo(self, lbl.rect().topLeft())
        # 比图标稍大一圈的外接环
        pad = 5
        x = top_left.x() - pad
        y = top_left.y() - pad
        d = lbl.width() + pad * 2
        rect = QRectF(x, y, d, d)
        # 用 conical 渐变让弧首尾自然渐隐，整体随 angle 旋转
        grad = QConicalGradient(rect.center(), -self._ring_angle)
        head = QColor(_BLUE)
        tail = QColor(_BLUE)
        tail.setAlpha(0)
        grad.setColorAt(0.0, head)
        grad.setColorAt(0.28, head)
        grad.setColorAt(0.30, tail)
        grad.setColorAt(1.0, tail)
        pen = QPen(QBrush(grad), 2.2)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawArc(rect, 0, 360 * 16)

    def closeEvent(self, e):  # noqa: N802
        """关闭时停掉旋转定时器，避免遗留 QTimer 在窗口析构后回调。"""
        if getattr(self, "_spin_timer", None) is not None:
            self._spin_timer.stop()
        super().closeEvent(e)

    def hideEvent(self, e):  # noqa: N802
        if getattr(self, "_spin_timer", None) is not None:
            self._spin_timer.stop()
        super().hideEvent(e)

    def _paint_glow(self, p: QPainter, x: int, y: int, size: int,
                    color: QColor) -> None:
        grad = QRadialGradient(QPointF(x + size / 2, y + size / 2), size / 2)
        grad.setColorAt(0.0, color)
        c2 = QColor(color)
        c2.setAlpha(0)
        grad.setColorAt(0.72, c2)
        grad.setColorAt(1.0, c2)
        p.fillRect(QRect(x, y, size, size), QBrush(grad))

    def _paint_progress_bar(self, p: QPainter) -> None:
        holder = self._bar_holder
        if holder is None:
            return
        top_left = holder.mapTo(self, holder.rect().topLeft())
        bw = holder.width()
        bh = max(3, holder.height())
        x, y = top_left.x(), top_left.y()
        # 轨道
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(16, 19, 36, 200))
        p.drawRoundedRect(x, y, bw, bh, 2, 2)
        # 填充
        fw = int(bw * self._progress)
        if fw > 0:
            grad = QLinearGradient(x, 0, x + bw, 0)
            grad.setColorAt(0.0, QColor(_BLUE))
            grad.setColorAt(0.5, QColor(_PERIW))
            grad.setColorAt(1.0, QColor(_MINT))
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(x, y, fw, bh, 2, 2)
