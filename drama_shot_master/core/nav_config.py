"""导航配置单一事实源：扁平项目级导航项、门禁阶段映射、容器页 tab 细分、图标映射。

阶段C Wave2a：导航由「8功能/4阶段分组」重构为「扁平项目级 6 项」——
概览 / 剧本创作 / 资源库 / 分镜板 / 视频生成 / 视频后期。
其中分镜板、视频后期为 QTabWidget 容器页，内部仍复用既有 8 个底层 panel
（imggen/split/combine/trim/dubbing/soundtrack…），故底层 FUNCS/PHASES 概念
作为「内部细分」保留（供容器页装配 + 旧门禁逻辑兼容），但侧栏不再直接用它们。

图标用本地 SVG 文件名，由 icon_path() 解析为绝对路径，
保持本模块 Qt-free 以便纯逻辑单测。
"""
from __future__ import annotations
from pathlib import Path

# ====================================================================== #
# 扁平项目级导航（Wave2a 新增）—— 顺序即侧栏从上到下
# ====================================================================== #

# (显示名, nav_key)；顺序即侧栏从上到下。概览置顶、设置/帮助另在底部固定。
NAV_ITEMS = [
    ("概览", "overview"),
    ("剧本创作", "screenwriter"),
    ("资源库", "asset_library"),
    ("分镜板", "storyboard"),
    ("视频生成", "video_gen"),
    ("视频后期", "video_post"),
]

# nav_key → manifest.STAGE_NAMES 门禁阶段。
# overview 不门禁（不在表内）。video_gen / video_post 同属 production 阶段。
NAV_STAGE = {
    "screenwriter": "screenwriter",
    "asset_library": "assets",
    "storyboard": "storyboard",
    "video_gen": "production",
    "video_post": "production",
}

# 分镜板容器页 tab：(底层 panel key, tab 中文标题)，顺序即 tab 从左到右。
STORYBOARD_TABS = [
    ("imggen", "出图"),
    ("split", "拆图"),
    ("combine", "拼图"),
    ("trim", "裁边"),
]

# 视频后期容器页 tab：(底层 panel key, tab 中文标题)。
VIDEOPOST_TABS = [
    ("compose", "智能转场"),
    ("dubbing", "配音"),
    ("soundtrack", "配乐"),
]

# ====================================================================== #
# 底层功能细分（容器页装配 + 旧门禁兼容）—— 侧栏不再直接渲染
# ====================================================================== #

# (显示名, key)；底层真实 panel，由 app_shell 构造后塞进容器页或直接作为页。
FUNCS = [
    ("编剧", "screenwriter"),
    ("拆图", "split"),
    ("拼图", "combine"),
    ("裁边", "trim"),
    ("出图", "imggen"),
    ("生视频", "video_gen"),
    ("智能转场", "compose"),
    ("配音", "dubbing"),
    ("配乐", "soundtrack"),
]

# 旧流程阶段分组：(阶段标题, [key, ...])。供旧门禁/兼容逻辑反查；侧栏不再渲染。
PHASES = [
    ("⓪ 剧本创作", ["screenwriter"]),
    ("① 素材准备", ["split", "combine", "trim"]),
    ("② 分镜创作", ["imggen"]),
    ("③ 视频出片", ["video_gen", "compose", "dubbing", "soundtrack"]),
]

# 批处理类（主区：网格+参数+执行）vs 任务管理类（主区：任务列表，双击开窗）
BATCH_KEYS = {"split", "combine", "trim"}
TASK_KEYS = {"imggen", "video_gen", "soundtrack", "dubbing", "screenwriter", "compose"}

_ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"

# func_key → SVG 文件名（底层功能；icon_path() 解析为绝对路径）。
# 保持与 FUNCS 一一对应（旧契约）；扁平导航专属 key 的图标见 NAV_ICONS。
ICONS = {
    "screenwriter": "pen.svg",
    "split": "cut.svg",
    "combine": "photo.svg",
    "trim": "erase.svg",
    "imggen": "palette.svg",
    "video_gen": "video.svg",
    "soundtrack": "music.svg",
    "dubbing": "mic.svg",
    "compose": "video.svg",
}

# 扁平导航专属 key → SVG 文件名（overview/asset_library/storyboard/video_post）。
# 复用底层功能图标也并入，便于侧栏统一查 nav_icon()。
NAV_ICONS = {
    "overview": "home.svg",
    "screenwriter": "pen.svg",
    "asset_library": "photo.svg",
    "storyboard": "palette.svg",
    "video_gen": "video.svg",
    "video_post": "mic.svg",
}
ICON_SETTINGS = "settings.svg"
ICON_HELP = "help.svg"


def icon_path(filename: str) -> "Path | None":
    """assets/icons/<filename> 的绝对 Path；缺失返回 None。"""
    p = _ICON_DIR / filename
    return p if p.exists() else None


def nav_icon(nav_key: str) -> str:
    """nav_key → SVG 文件名；缺失返回空串（侧栏据此跳过设图标，不崩）。"""
    return NAV_ICONS.get(nav_key, ICONS.get(nav_key, ""))


# 功能名映射（key → 显示名）：扁平导航项 + 底层功能，便于面包屑/标题查询。
LABELS = {key: label for label, key in FUNCS}
LABELS.update({key: label for label, key in NAV_ITEMS})


# ---- 门禁元数据：阶段标题 ↔ manifest.STAGE_NAMES 显式映射 ---------------- #
#
# manifest.STAGE_NAMES = ("screenwriter", "assets", "storyboard", "production")
# 与旧 PHASES 一一对位（顺序即制作管线先后）。显式列出避免日后调序时静默错位。
# 本模块保持 Qt-free，故此处复制英文阶段名常量（与 manifest.STAGE_NAMES 等价），
# 不在导航壳里硬依赖 compass.manifest，单测另行校验两者自洽。
PHASE_STAGE_MAP = {
    "⓪ 剧本创作": "screenwriter",
    "① 素材准备": "assets",
    "② 分镜创作": "storyboard",
    "③ 视频出片": "production",
}

# func_key → STAGE_NAMES 之一：该底层功能可达的阶段 state 门禁所在。
# 由 PHASES 分组 × PHASE_STAGE_MAP 推导（每功能恰属一个阶段）。
PHASE_GATES = {
    key: PHASE_STAGE_MAP[title]
    for title, keys in PHASES
    for key in keys
}

# func_key → PHASES 阶段标题（中文 emoji）反查表。
_PHASE_OF = {key: title for title, keys in PHASES for key in keys}


def phase_of(func_key: str) -> "str | None":
    """func_key → 所属 PHASES 阶段标题（中文 emoji）；未知 → None。

    亦兼容扁平 nav_key：若 func_key 是 nav_key（如 overview/asset_library/
    video_post），返回其 NAV 显示名作为面包屑前缀。
    """
    if func_key in _PHASE_OF:
        return _PHASE_OF[func_key]
    if func_key in NAV_STAGE or func_key == "overview":
        return LABELS.get(func_key)
    return None


def stage_of(func_key: str) -> "str | None":
    """func_key → 门禁阶段（STAGE_NAMES 之一）；未知 → None。

    兼容扁平 nav_key（优先查 NAV_STAGE）。
    """
    if func_key in NAV_STAGE:
        return NAV_STAGE[func_key]
    return PHASE_GATES.get(func_key)


def gated_funcs(stage: str) -> list:
    """stage（STAGE_NAMES 之一）→ 该阶段门禁下的 func_key 列表（按 FUNCS 顺序）。

    未知阶段返回空列表（不抛）。
    """
    return [key for _label, key in FUNCS if PHASE_GATES.get(key) == stage]


def nav_gated(stage: str) -> list:
    """stage（STAGE_NAMES 之一）→ 该阶段下的扁平 nav_key 列表（按 NAV_ITEMS 顺序）。

    用于扁平侧栏门禁：production 阶段会返回 [video_gen, video_post] 两项。
    未知阶段返回空列表（不抛）。
    """
    return [key for _label, key in NAV_ITEMS if NAV_STAGE.get(key) == stage]
