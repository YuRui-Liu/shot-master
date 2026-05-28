# drama_shot_master/ui/styles/tokens_light.py
"""浅色主题 token。与 tokens_dark 一一对应、键名完全一致。"""

LIGHT: dict[str, str] = {
    # 背景
    "bg":          "#fafafa",
    "bg_alt":      "#ffffff",
    "bg_elevated": "#f5f6f7",
    "border":      "#dadce0",
    # 文字
    "fg":          "#1f2024",
    "fg_muted":    "#5f6368",
    # 强调
    "accent":      "#0066cc",
    "accent_text": "#ffffff",
    "select_bg":   "#cce0ff",
    # 状态色
    "status_running": "#1a73e8",
    "status_failed":  "#d93025",
    "status_done":    "#1e8e3e",
    "status_idle":    "#5f6368",
    # 原生标题栏
    "titlebar_bg": "#fafafa",
    "titlebar_fg": "#1f2024",
    # 几何
    "radius":      "6px",
}
