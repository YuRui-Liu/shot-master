"""导航配置单一事实源：功能列表、流程阶段分组、图标映射。

新旧外壳（main_window / app_shell）共享，避免顺序/分组出现两份。
图标用本地 SVG 文件名，由 icon_path() 解析为绝对路径，
保持本模块 Qt-free 以便纯逻辑单测。
"""
from __future__ import annotations
from pathlib import Path

# (显示名, key)；顺序即侧栏从上到下顺序，须与 PHASES 展平后一致。
FUNCS = [
    ("编剧", "screenwriter"),
    ("拆图", "split"),
    ("拼图", "combine"),
    ("裁边", "trim"),
    ("出图", "imggen"),
    ("生视频", "video_gen"),
    ("配音", "dubbing"),
    ("配乐", "soundtrack"),
]

# 流程阶段：(阶段标题, [key, ...])。标题带编号体现制作管线先后。
PHASES = [
    ("⓪ 剧本创作", ["screenwriter"]),
    ("① 素材准备", ["split", "combine", "trim"]),
    ("② 分镜创作", ["imggen"]),
    ("③ 视频出片", ["video_gen", "dubbing", "soundtrack"]),
]

# 批处理类（主区：网格+参数+执行）vs 任务管理类（主区：任务列表，双击开窗）
BATCH_KEYS = {"split", "combine", "trim"}
TASK_KEYS = {"imggen", "video_gen", "soundtrack", "dubbing", "screenwriter"}

_ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"

# key → SVG 文件名（icon_path() 解析为绝对路径）
ICONS = {
    "screenwriter": "pen.svg",
    "split": "cut.svg",
    "combine": "photo.svg",
    "trim": "erase.svg",
    "imggen": "palette.svg",
    "video_gen": "video.svg",
    "soundtrack": "music.svg",
    "dubbing": "mic.svg",
}
ICON_SETTINGS = "settings.svg"
ICON_HELP = "help.svg"


def icon_path(filename: str) -> "Path | None":
    """assets/icons/<filename> 的绝对 Path；缺失返回 None。"""
    p = _ICON_DIR / filename
    return p if p.exists() else None


# 功能名映射（key → 显示名），便于面包屑/标题查询
LABELS = {key: label for label, key in FUNCS}


# ---- 门禁元数据：PHASES 中文 emoji 标题 ↔ manifest.STAGE_NAMES 显式映射 -----
#
# manifest.STAGE_NAMES = ("screenwriter", "assets", "storyboard", "production")
# 与本模块 PHASES 一一对位（顺序即制作管线先后）：
#   ⓪ 剧本创作 → screenwriter
#   ① 素材准备 → assets
#   ② 分镜创作 → storyboard
#   ③ 视频出片 → production
# 显式列出而非 zip(PHASES, STAGE_NAMES)，避免日后任一侧调序时静默错位。
# 本模块保持 Qt-free，故此处复制英文阶段名常量（与 manifest.STAGE_NAMES 等价），
# 不在导航壳里硬依赖 compass.manifest，单测另行校验两者自洽。
PHASE_STAGE_MAP = {
    "⓪ 剧本创作": "screenwriter",
    "① 素材准备": "assets",
    "② 分镜创作": "storyboard",
    "③ 视频出片": "production",
}

# func_key → STAGE_NAMES 之一：该功能可达的阶段 state 门禁所在。
# 由 PHASES 分组 × PHASE_STAGE_MAP 推导（每功能恰属一个阶段）。
PHASE_GATES = {
    key: PHASE_STAGE_MAP[title]
    for title, keys in PHASES
    for key in keys
}

# func_key → PHASES 阶段标题（中文 emoji）反查表。
_PHASE_OF = {key: title for title, keys in PHASES for key in keys}


def phase_of(func_key: str) -> "str | None":
    """func_key → 所属 PHASES 阶段标题（中文 emoji）；未知 → None。"""
    return _PHASE_OF.get(func_key)


def stage_of(func_key: str) -> "str | None":
    """func_key → 门禁阶段（STAGE_NAMES 之一）；未知 → None。"""
    return PHASE_GATES.get(func_key)


def gated_funcs(stage: str) -> list:
    """stage（STAGE_NAMES 之一）→ 该阶段门禁下的 func_key 列表（按 FUNCS 顺序）。

    未知阶段返回空列表（不抛）。
    """
    return [key for _label, key in FUNCS if PHASE_GATES.get(key) == stage]
