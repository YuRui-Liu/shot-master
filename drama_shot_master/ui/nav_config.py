"""导航配置单一事实源：功能列表、流程阶段分组、图标映射。

新旧外壳（main_window / app_shell）共享，避免顺序/分组出现两份。
图标用 qfluentwidgets.FluentIcon 名称字符串，装配时再解析为枚举，
保持本模块 Qt-free 以便纯逻辑单测。
"""
from __future__ import annotations

# (显示名, key)；顺序即侧栏从上到下顺序，须与 PHASES 展平后一致。
FUNCS = [
    ("拆图", "split"),
    ("拼图", "combine"),
    ("去白边", "trim"),
    ("图片生成", "imggen"),
    ("视频生成", "video_gen"),
    ("配乐", "soundtrack"),
    ("配音", "dubbing"),
]

# 流程阶段：(阶段标题, [key, ...])。标题带编号体现制作管线先后。
PHASES = [
    ("① 素材准备", ["split", "combine", "trim"]),
    ("② 分镜创作", ["imggen"]),
    ("③ 视频出片", ["video_gen", "soundtrack", "dubbing"]),
]

# 批处理类（主区：网格+参数+执行）vs 任务管理类（主区：任务列表，双击开窗）
BATCH_KEYS = {"split", "combine", "trim"}
TASK_KEYS = {"imggen", "video_gen", "soundtrack", "dubbing"}

# key → FluentIcon 成员名（装配时 getattr(FluentIcon, name)）
ICONS = {
    "split": "CUT",
    "combine": "PHOTO",
    "trim": "ERASE_TOOL",
    "imggen": "PALETTE",
    "video_gen": "VIDEO",
    "soundtrack": "MUSIC",
    "dubbing": "MICROPHONE",
}

# 功能名映射（key → 显示名），便于面包屑/标题查询
LABELS = {key: label for label, key in FUNCS}
