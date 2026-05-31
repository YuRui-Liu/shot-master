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
    QBrush, QPen, QPixmap, QFont,
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


class _MiniBar(QWidget):
    """单步清单行右侧的迷你进度条（复刻 mockup .mini / .mini i）。

    done → 满（蓝紫渐变）；active → 随相位左右伸缩动画（复刻 @keyframes load）；
    pending → 空。QSS 渐变在 Win11 不渲染，故 QPainter 自绘。phase 由外部动画驱动。
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedHeight(3)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._state = "pending"
        self._phase = 0.0           # [0,1) active 动画相位

    def set_state(self, state: str) -> None:
        self._state = state
        self.update()

    def set_phase(self, phase: float) -> None:
        if self._state == "active":
            self._phase = phase
            self.update()

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        # 轨道（mockup .mini 背景 #12162a）
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0x12, 0x16, 0x2a))
        p.drawRoundedRect(0, 0, w, h, 1.5, 1.5)
        # 填充比例：done=1；active 在 0.2↔0.75↔0.45 间往返；pending=0
        if self._state == "done":
            frac = 1.0
        elif self._state == "active":
            # 复刻 @keyframes load{0%:20% 50%:75% 100%:45%} 的三角往返
            t = self._phase
            if t < 0.5:
                frac = 0.20 + (0.75 - 0.20) * (t / 0.5)
            else:
                frac = 0.75 + (0.45 - 0.75) * ((t - 0.5) / 0.5)
        else:
            frac = 0.0
        fw = int(w * frac)
        if fw > 0:
            grad = QLinearGradient(0, 0, w, 0)
            grad.setColorAt(0.0, QColor(_BLUE))
            grad.setColorAt(1.0, QColor(_PERIW))
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(0, 0, fw, h, 1.5, 1.5)
        p.end()


class _GradientTitle(QLabel):
    """标题：用横向渐变填充文字（复刻 mockup .title 的 background-clip:text）。

    CSS：linear-gradient(90deg,#ffffff,#c7cdf2 60%,periw)。QLabel 默认平铺文字色无法
    渐变，故重写 paintEvent 用 QLinearGradient 作画笔填字。
    """

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAlignment(Qt.AlignCenter)

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        grad = QLinearGradient(0, 0, self.width(), 0)
        grad.setColorAt(0.0, QColor("#ffffff"))
        grad.setColorAt(0.6, QColor("#c7cdf2"))
        grad.setColorAt(1.0, QColor(_PERIW))
        p.setPen(QPen(QBrush(grad), 0))
        p.setFont(self.font())
        p.drawText(self.rect(), int(self.alignment()), self.text())
        p.end()


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
        lay.addSpacing(4)

        # 右侧迷你进度条（mockup .mini，flex:1 占满剩余宽）
        self._mini = _MiniBar()
        lay.addWidget(self._mini, 1)

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
        self._mini.set_state(state)

    def set_mini_phase(self, phase: float) -> None:
        self._mini.set_phase(phase)

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

        # 动画时基：QTimer ~60fps 自增 elapsed(ms)，各动画按各自周期取相位。
        # 复刻 mockup 的多条 CSS 动画：
        #   .mark .ring  → spin 2.4s linear（图标外圈旋转弧）
        #   .pill .dot   → blink 1.2s（LOADING 圆点闪烁）
        #   .st.active .mini i → load 1.6s（活跃步迷你条往返）
        #   .bar i       → shimmer 2s（底部主进度条流光）
        self._elapsed_ms = 0.0
        self._ring_angle = 0.0          # 兼容旧字段/测试，由 elapsed 推导
        self._spin_timer = QTimer(self)
        self._spin_timer.setInterval(16)            # ≈60fps
        self._spin_timer.timeout.connect(self._advance_anim)
        self._spin_timer.start()

        self._build_ui()

    def _advance_anim(self) -> None:
        """每帧推进时基并请求重绘（驱动环弧 / 迷你条 / 流光）。"""
        self._elapsed_ms += self._spin_timer.interval()
        # 环：2.4s 一圈 = 150°/s（复刻 CSS spin 2.4s linear）
        self._ring_angle = (self._elapsed_ms / 2400.0 * 360.0) % 360.0
        # 活跃步迷你条相位：1.6s 周期（复刻 @keyframes load 1.6s）
        mini_phase = (self._elapsed_ms % 1600.0) / 1600.0
        for r in self._stage_rows:
            r.set_mini_phase(mini_phase)
        self.update()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(0)

        # 顶部行：左 LOADING pill（含闪烁圆点）+ 右「跳过 →」
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        # 文本前留全角空格给自绘闪烁圆点（_paint_pill_dot 画在左 padding 内）
        self._pill = QLabel("  LOADING")
        self._pill.setObjectName("SplashPill")
        self._pill.setStyleSheet(
            f"color:{_BLUE};font-size:10px;font-weight:600;letter-spacing:1.2px;"
            f"border:1px solid #294a78;background:rgba(74,158,255,0.10);"
            f"border-radius:10px;padding:2px 10px 2px 14px;"
        )
        top.addWidget(self._pill)
        top.addStretch(1)
        self._skip_lbl = QLabel("跳过 →")
        self._skip_lbl.setObjectName("SplashSkip")
        self._skip_lbl.setStyleSheet(f"color:{_FAINT};font-size:11px;")
        top.addWidget(self._skip_lbl)
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

        self._title_lbl = _GradientTitle(_BRAND_TITLE)
        self._title_lbl.setObjectName("SplashTitle")
        tf = self._title_lbl.font()
        tf.setPixelSize(19)
        tf.setWeight(QFont.Weight.DemiBold)  # ≈750；Qt 字重档位最接近的粗体
        tf.setLetterSpacing(QFont.AbsoluteSpacing, 0.5)
        self._title_lbl.setFont(tf)
        brand.addWidget(self._title_lbl)

        self._version_lbl = QLabel(_VERSION_LINE)
        self._version_lbl.setAlignment(Qt.AlignCenter)
        self._version_lbl.setStyleSheet(
            f"color:{_SUB};font-size:10px;letter-spacing:3px;"
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

        # 极淡蓝色网格（复刻 mockup .grid：34px 网格，opacity ~.05）
        self._paint_grid(p, w, h)

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

        # 品牌图标外圈旋转环（复刻 .mark .ring：蓝顶 + 紫右，余透明，旋转）
        self._paint_spinner_ring(p)

        # LOADING pill 圆点闪烁（复刻 .pill .dot blink 1.2s）
        self._paint_pill_dot(p)

        # 主进度条（底部 holder 位置自绘，含流光 shimmer）
        self._paint_progress_bar(p)

        p.end()

    def _paint_grid(self, p: QPainter, w: int, h: int) -> None:
        """极淡蓝网格线（mockup .grid：34px 间距，opacity ~.05 → alpha≈13）。"""
        pen = QPen(QColor(0x9b, 0xb0, 0xff, 13))
        pen.setWidth(1)
        p.setPen(pen)
        step = 34
        x = step
        while x < w:
            p.drawLine(x, 0, x, h)
            x += step
        y = step
        while y < h:
            p.drawLine(0, y, w, y)
            y += step

    def _paint_pill_dot(self, p: QPainter) -> None:
        """LOADING pill 左侧圆点 + blink（1.2s 周期透明度 1↔.3）。"""
        pill = getattr(self, "_pill", None)
        if pill is None:
            return
        # blink：三角波 1↔.3↔1
        t = (self._elapsed_ms % 1200.0) / 1200.0
        opacity = 1.0 - 0.7 * (1.0 - abs(2.0 * t - 1.0))
        c = QColor(_BLUE)
        c.setAlphaF(max(0.0, min(1.0, opacity)))
        # 圆点画在 pill 文本起始处（左 padding 内）
        tl = pill.mapTo(self, pill.rect().topLeft())
        cx = tl.x() + 11
        cy = tl.y() + pill.height() / 2.0
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawEllipse(QPointF(cx, cy), 3.0, 3.0)

    def _paint_spinner_ring(self, p: QPainter) -> None:
        """绕品牌图标旋转的双色环（复刻 .mark .ring：top=蓝 / right=紫，余透明）。"""
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
        p.setBrush(Qt.NoBrush)
        # Qt drawArc：0° = 3点钟方向，逆时针为正；角度 * 16。
        # 复刻 CSS：border-top-color(顶 12点) + border-right-color(右 3点)，各占 ~90°，
        # 整体随 -ring_angle 顺时针旋转（CSS spin 顺时针）。
        base = -self._ring_angle
        # 顶段（蓝）：以 12 点(90°) 为中心的 90° 弧
        pen_blue = QPen(QColor(_BLUE), 1.6)
        pen_blue.setCapStyle(Qt.FlatCap)
        p.setPen(pen_blue)
        p.drawArc(rect, int((base + 45) * 16), int(90 * 16))
        # 右段（紫）：以 3 点(0°) 为中心的 90° 弧
        pen_periw = QPen(QColor(_PERIW), 1.6)
        pen_periw.setCapStyle(Qt.FlatCap)
        p.setPen(pen_periw)
        p.drawArc(rect, int((base - 45) * 16), int(90 * 16))

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
        # 填充：宽度跟随真实进度；蓝→紫→薄荷渐变随时间横向流动（复刻 shimmer 2s）。
        fw = int(bw * self._progress)
        if fw > 0:
            # background-size:200% → 渐变跨度 = 2×条宽；position 在 2s 内平移一个条宽。
            shift = (self._elapsed_ms % 2000.0) / 2000.0 * bw
            g0 = x - bw + shift
            grad = QLinearGradient(g0, 0, g0 + 2 * bw, 0)
            grad.setColorAt(0.0, QColor(_BLUE))
            grad.setColorAt(0.25, QColor(_PERIW))
            grad.setColorAt(0.5, QColor(_MINT))
            grad.setColorAt(0.75, QColor(_PERIW))
            grad.setColorAt(1.0, QColor(_BLUE))
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(x, y, fw, bh, 2, 2)
