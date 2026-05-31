"""文件罗盘协议 · 项目目录布局 + 路径拼装（split_unit 感知）。

三层 manifest 的「路径地基」：把项目根、project.json、各产物路径、
标准子目录树（characters/scenes/props/assets/shots/clips/soundtrack/
exports/归档）统一收口；并按 params.split_unit 切换单位 ID 前缀与子目录。

原则「升级不推倒」：兼容现有平铺产物命名
（创意.json / 剧本.json / 剧本_E1.md / 分镜_E1.json / prompts/E1/），
逐集/逐单位产物路径**包装** screenwriter_agent.core.paths，不重复定义。

纯逻辑、无 Qt，全单测。字段/命名形状照 research §2.3 / §2.4。
"""
from __future__ import annotations

from pathlib import Path

# 现有产物路径约定的权威定义源——本模块只做包装/扩展，不重复实现
from screenwriter_agent.core import paths as _sw

# project.json 在项目目录下的固定文件名（与 manifest.MANIFEST_FILENAME 对齐）
MANIFEST_FILENAME = "project.json"
# 全局注册表（projects_root 下）
REGISTRY_FILENAME = "index.json"
# 各资源种类的引用索引文件名
REF_INDEX_FILENAME = "ref_index.json"

# 标准资源种类（各有独立 ref_index.json 与子目录）
RESOURCE_KINDS = ("characters", "scenes", "props")

# split_unit → 单位 ID 前缀 + 序号补零位宽
# episode 不补零（沿用现有 E1/E2…）；segment 两位；shot 三位
_SPLIT_UNIT_RULES: dict[str, tuple[str, int]] = {
    "episode": ("E", 0),
    "segment": ("SEG", 2),
    "shot": ("S", 3),
}

# 逐镜底图/视频碎片的三位补零位宽（shot001…）
SHOT_PAD = 3


# ---- 项目根 / 注册表 / 清单 -------------------------------------------

def project_dir(projects_root: Path, project_id: str, slug: str = "") -> Path:
    """项目目录 = <root>/{ID}_{slug}/；无 slug 时仅 ID。"""
    name = f"{project_id}_{slug}" if slug else project_id
    return Path(projects_root) / name


def registry_index_path(projects_root: Path) -> Path:
    """全局注册表 index.json。"""
    return Path(projects_root) / REGISTRY_FILENAME


def manifest_path(project_dir: Path) -> Path:
    """项目清单 project.json。"""
    return Path(project_dir) / MANIFEST_FILENAME


# ---- 标准子目录树 -----------------------------------------------------

def characters_dir(project_dir: Path) -> Path:
    return Path(project_dir) / "characters"


def scenes_dir(project_dir: Path) -> Path:
    return Path(project_dir) / "scenes"


def props_dir(project_dir: Path) -> Path:
    return Path(project_dir) / "props"


def assets_dir(project_dir: Path) -> Path:
    """用户导入素材。"""
    return Path(project_dir) / "assets"


def soundtrack_dir(project_dir: Path) -> Path:
    """配乐项目级单例。"""
    return Path(project_dir) / "soundtrack"


def exports_dir(project_dir: Path) -> Path:
    """成片 + video_index.json。"""
    return Path(project_dir) / "exports"


def archive_dir(project_dir: Path) -> Path:
    """大改版本快照——中文名 归档/。"""
    return Path(project_dir) / "归档"


def ref_index_path(project_dir: Path, kind: str) -> Path:
    """某资源种类（characters/scenes/props）的 ref_index.json。"""
    if kind not in RESOURCE_KINDS:
        raise ValueError(
            f"未知资源种类 {kind!r}，应为 {RESOURCE_KINDS} 之一"
        )
    return Path(project_dir) / kind / REF_INDEX_FILENAME


# ---- 兼容现有平铺产物（包装 screenwriter_agent.core.paths） -----------

def idea_path(project_dir: Path) -> Path:
    """创意.json 写入路径。"""
    return _sw.idea_write_path(Path(project_dir))


def script_index_path(project_dir: Path) -> Path:
    """剧本集索引 剧本.json。"""
    return _sw.script_index_path(Path(project_dir))


def script_unit_path(project_dir: Path, unit_id: str) -> Path:
    """逐单位剧本：剧本_{unit_id}.md（unit_id 如 E1/SEG01/S001）。"""
    return _sw.script_episode_path(Path(project_dir), unit_id)


def storyboard_unit_path(project_dir: Path, unit_id: str) -> Path:
    """逐单位分镜：分镜_{unit_id}.json。"""
    return _sw.storyboard_episode_path(Path(project_dir), unit_id)


def image_prompts_dir(project_dir: Path, unit_id: str) -> Path:
    """出图 prompt 目录：prompts/{unit_id}/。"""
    return _sw.episode_prompts_dir(Path(project_dir), unit_id)


def video_prompts_dir(project_dir: Path, unit_id: str) -> Path:
    """视频 prompt 目录：video_prompts/{unit_id}/。"""
    return _sw.video_prompts_dir(Path(project_dir), unit_id)


def audio_prompts_dir(project_dir: Path, unit_id: str) -> Path:
    """音频 prompt 目录：audio_prompts/{unit_id}/。"""
    return _sw.audio_prompts_dir(Path(project_dir), unit_id)


def shots_dir(project_dir: Path, unit_id: str) -> Path:
    """② 分镜底图/选帧：shots/{unit_id}/。"""
    return Path(project_dir) / "shots" / unit_id


def clips_dir(project_dir: Path, unit_id: str) -> Path:
    """③ 视频碎片：clips/{unit_id}/。"""
    return Path(project_dir) / "clips" / unit_id


# ---- split_unit 感知：ID 前缀 / 拼装 ----------------------------------

def unit_prefix(split_unit: str) -> str:
    """split_unit → 单位 ID 前缀（episode→E / segment→SEG / shot→S）。"""
    rule = _SPLIT_UNIT_RULES.get(split_unit)
    if rule is None:
        raise ValueError(
            f"未知 split_unit {split_unit!r}，应为 {tuple(_SPLIT_UNIT_RULES)} 之一"
        )
    return rule[0]


def make_unit_id(split_unit: str, n: int) -> str:
    """单位 ID 拼装：前缀 + 序号（按 split_unit 补零）。

    episode 不补零（E1/E12）；segment 两位（SEG01）；shot 三位（S001）。
    """
    rule = _SPLIT_UNIT_RULES.get(split_unit)
    if rule is None:
        raise ValueError(
            f"未知 split_unit {split_unit!r}，应为 {tuple(_SPLIT_UNIT_RULES)} 之一"
        )
    prefix, pad = rule
    num = str(n) if pad <= 0 else str(n).zfill(pad)
    return f"{prefix}{num}"


# ---- 三位补零 shotNNN（逐镜底图/prompt 文件名） -----------------------

def shot_stem(n: int) -> str:
    """逐镜文件名干：shot001（三位补零）。"""
    return f"shot{str(n).zfill(SHOT_PAD)}"


def shot_image_path(project_dir: Path, unit_id: str, n: int) -> Path:
    """逐镜底图：shots/{unit_id}/shot001.png。"""
    return shots_dir(project_dir, unit_id) / f"{shot_stem(n)}.png"


def shot_prompt_path(project_dir: Path, unit_id: str, n: int) -> Path:
    """逐镜出图 prompt：prompts/{unit_id}/shot001.txt。"""
    return image_prompts_dir(project_dir, unit_id) / f"{shot_stem(n)}.txt"
