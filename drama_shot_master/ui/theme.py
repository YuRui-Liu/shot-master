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


def load_stylesheet(name: str = "dark") -> str:
    """读取 styles/{name}.qss 内容；文件缺失时返回空串（退回 Qt 默认外观）。"""
    p = _QSS_DIR / f"{name}.qss"
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return ""


def apply_theme(app, name: str = "dark") -> None:
    """把主题样式表应用到 QApplication。"""
    qss = load_stylesheet(name)
    if qss:
        app.setStyleSheet(qss)


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


# 影视冷蓝（spec §5）；浅色切换在 Phase 3 设置页接入
THEME_ACCENT = "#2563EB"


def init_fluent_theme(app, dark: bool = True, accent: str = THEME_ACCENT) -> "QColor":
    """初始化 PyQt-Fluent-Widgets 全局主题：深/浅 + 主题色。

    返回设置后的主题色 QColor。在 apply_theme(app) 之后调用，
    让 Fluent 控件接管自身配色（QSS 仍可覆盖非 Fluent 控件）。
    """
    # app 形参保留以与 apply_theme(app) 调用点对称；当前 Fluent 全局 API 不需要它
    from qfluentwidgets import setTheme, setThemeColor, Theme
    from PySide6.QtGui import QColor
    setTheme(Theme.DARK if dark else Theme.LIGHT)
    c = QColor(accent)
    setThemeColor(c)
    return c
