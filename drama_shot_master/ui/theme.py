"""全局 QSS 主题加载。

深色·影视专业主题；样式表见 styles/dark.qss。
"""
from __future__ import annotations

import sys
from pathlib import Path

_QSS_DIR = Path(__file__).resolve().parent / "styles"
_ASSET_DIR = Path(__file__).resolve().parent.parent / "assets"

# 主题主色（与 dark.qss 一致），供原生标题栏配色复用
TITLEBAR_BG = "#1e1f22"
TITLEBAR_FG = "#e8eaed"

# Windows DWM 属性常量
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20    # 旧版 build(<19041) 用 19
_DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
_DWMWA_BORDER_COLOR = 34               # Win11 22000+
_DWMWA_CAPTION_COLOR = 35              # Win11 22000+
_DWMWA_TEXT_COLOR = 36                 # Win11 22000+


def _colorref(hex_str: str) -> int:
    """#RRGGBB → Win32 COLORREF(0x00BBGGRR)。"""
    h = hex_str.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (b << 16) | (g << 8) | r


def apply_dark_titlebar(widget,
                        caption_hex: str = TITLEBAR_BG,
                        text_hex: str = TITLEBAR_FG) -> None:
    """把原生标题栏改成深色（仅 Windows 生效，其它平台静默跳过）。

    需在窗口已有原生句柄时调用（show 之后最稳）。
    任何失败（旧系统 / API 缺失）都静默退回系统默认外观。
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        hwnd = int(widget.winId())
        dwm = ctypes.windll.dwmapi
        # 64 位 HWND 必须声明 argtypes，否则句柄被截断
        dwm.DwmSetWindowAttribute.argtypes = [
            wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        dwm.DwmSetWindowAttribute.restype = ctypes.c_long

        def _set(attr: int, value: int) -> None:
            v = ctypes.c_int(value)
            dwm.DwmSetWindowAttribute(
                wintypes.HWND(hwnd), wintypes.DWORD(attr),
                ctypes.byref(v), ctypes.sizeof(v))

        # 1) 深色模式（新旧两个属性都试，无效的那个返回错误码但无害）
        _set(_DWMWA_USE_IMMERSIVE_DARK_MODE, 1)
        _set(_DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, 1)
        # 2) 精确配色（Win11 22000+；旧系统忽略，已由深色模式兜底）
        _set(_DWMWA_CAPTION_COLOR, _colorref(caption_hex))
        _set(_DWMWA_TEXT_COLOR, _colorref(text_hex))
        _set(_DWMWA_BORDER_COLOR, _colorref(caption_hex))
    except Exception:
        pass


def apply_titlebar(widget, name: str = "dark") -> None:
    """按主题给原生标题栏上色（Windows DWM；其它平台静默跳过）。
    替代 apply_dark_titlebar；从 token 读 caption/text 色。"""
    tokens = _tokens(name)
    apply_dark_titlebar(widget,
                        caption_hex=tokens.get("titlebar_bg", TITLEBAR_BG),
                        text_hex=tokens.get("titlebar_fg", TITLEBAR_FG))


def _tokens(name: str) -> dict:
    """name='dark'|'light' → token 字典；未知回退 dark。"""
    if name == "light":
        try:
            from drama_shot_master.ui.styles.tokens_light import LIGHT
            return LIGHT
        except ImportError:
            pass
    from drama_shot_master.ui.styles.tokens_dark import DARK
    return DARK


def load_stylesheet(name: str = "dark") -> str:
    """渲染 theme.qss.tpl + 对应 token；模板缺失返回空串。"""
    tpl_path = _QSS_DIR / "theme.qss.tpl"
    try:
        tpl = tpl_path.read_text(encoding="utf-8")
    except OSError:
        return ""
    try:
        return tpl.format(**_tokens(name))
    except KeyError:
        # token 缺失 → 退到 dark 兜底以免空白窗
        return tpl.format(**_tokens("dark"))


def apply_theme(app, name: str = "dark") -> None:
    """切主题样式表并强制 repolish 所有顶层窗（含 dock/对话框）。"""
    qss = load_stylesheet(name)
    if not qss:
        return
    app.setStyleSheet(qss)
    for w in app.topLevelWidgets():
        w.style().unpolish(w)
        w.style().polish(w)
        w.update()


def current_theme(cfg) -> str:
    """从 cfg 读 theme（默认 dark）。"""
    return getattr(cfg, "theme", "dark") or "dark"


def _find_app_icon_path(name: str = "app_icon"):
    """在 assets/ 下按 .ico→.png→.svg 找图标，返回 Path 或 None。"""
    for ext in (".ico", ".png", ".svg"):
        p = _ASSET_DIR / f"{name}{ext}"
        if p.exists():
            return p
    return None


def apply_window_icon(widget, name: str = "app_icon") -> None:
    """给窗口自身设图标——原生标题栏据此在软件名左侧显示 [图标]。"""
    p = _find_app_icon_path(name)
    if p:
        from PySide6.QtGui import QIcon
        widget.setWindowIcon(QIcon(str(p)))


def apply_app_icon(app, name: str = "app_icon") -> None:
    """设置全局窗口图标（所有窗口/对话框继承）。

    在 drama_shot_master/assets/ 下按 .ico → .png → .svg 顺序找 {name}.*；
    找不到则静默跳过（保持 Qt 默认图标）。Windows 任务栏首选 .ico（多尺寸）。
    """
    from PySide6.QtGui import QIcon
    p = _find_app_icon_path(name)
    if p:
        app.setWindowIcon(QIcon(str(p)))


# 状态字符串 → token key 映射
_STATUS_TOKEN = {
    "空闲":   "status_idle",
    "生成中": "status_running",
    "完成":   "status_done",
    "失败":   "status_failed",
}


def status_color(status: str, cfg=None) -> str:
    """状态字符串 → 当前主题对应的 hex 颜色。
    cfg 缺省时按 dark 取色（兼容 lib 调用无 cfg 上下文）。"""
    name = current_theme(cfg) if cfg is not None else "dark"
    tok = _STATUS_TOKEN.get(status, "status_idle")
    return _tokens(name).get(tok, "#9aa0a6")

