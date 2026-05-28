# drama_shot_master/ui/styles/tokens_dark.py
"""深色主题 token 单一源。所有颜色/尺寸常量在此声明，theme.qss.tpl 通过 .format()
消费。修改 token 前先确认 light 对应项是否要联动调整。"""

DARK: dict[str, str] = {
    # 背景
    "bg":          "#1e1f22",
    "bg_alt":      "#2b2d30",
    "bg_elevated": "#32353a",
    "border":      "#3a3d42",
    # 文字
    "fg":          "#e8eaed",
    "fg_muted":    "#9aa0a6",
    # 强调
    "accent":      "#4a9eff",
    "accent_text": "#ffffff",
    "select_bg":   "#2f5e96",
    # 状态色
    "status_running": "#4a9eff",
    "status_failed":  "#ff5c5c",
    "status_done":    "#4ec98f",
    "status_idle":    "#9aa0a6",
    # 原生标题栏
    "titlebar_bg": "#1e1f22",
    "titlebar_fg": "#e8eaed",
    # 几何
    "radius":      "6px",
}
