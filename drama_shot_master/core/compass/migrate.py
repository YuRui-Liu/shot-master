"""文件罗盘协议 · 现有项目迁移（平铺产物 → project.json 总线）。

把一个**无 project.json** 的旧项目目录（平铺产物：创意.json / 剧本.json /
剧本_E1.md / 分镜_E1.json / prompts/E1/ …，集 ID E1…）升级为带项目清单
总线的罗盘项目：扫描既有产物 → 推断 pipeline 阶段状态 / episodes 进度路径 /
artifacts 索引 → 生成 project.json（manifest.save_manifest）并可登记进
全局注册表 registry。

原则「升级不推倒」：只新增 project.json 总线层，绝不改既有文件名/集 ID。
幂等：已有 project.json → 原样加载返回、不覆盖、不重复登记。

纯逻辑、无 Qt，全单测。字段形状照 research §2.3。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from screenwriter_agent.core import paths as _sw

from . import paths as _cpaths
from .manifest import (
    EpisodeProgress,
    ProjectManifest,
    StageState,
    load_manifest,
    save_manifest,
)
from .registry import ProjectRegistry

# 目录名形如 {ID}_{slug} 时，从前缀抽 project_id（P-001_xxx → P-001）
_DIR_ID_RE = re.compile(r"^(P-\d+)(?:_.*)?$")
# 逐集剧本 文件名 剧本_E1.md → 集 ID
_SCRIPT_EP_RE = re.compile(r"^剧本_(E[1-9]\d*)\.md$")


def _infer_project_id(project_dir: Path) -> str:
    """从目录名前缀推断 project_id（P-001_xxx → P-001）；无前缀 → 空串。"""
    m = _DIR_ID_RE.match(project_dir.name)
    return m.group(1) if m else ""


def _read_json(path: Path) -> Optional[dict]:
    """安全读 JSON；缺失/坏 JSON/非 dict → None。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _infer_project_name(project_dir: Path, script_index: Optional[dict]) -> str:
    """项目名优先取 剧本.json.title，兜底 创意.json.title，再兜底目录 slug。"""
    if script_index and script_index.get("title"):
        return str(script_index["title"])
    idea_path = _sw.idea_read_path(project_dir)
    if idea_path is not None:
        idea = _read_json(idea_path)
        if idea and idea.get("title"):
            return str(idea["title"])
    # 兜底：目录名去掉 ID 前缀
    name = project_dir.name
    m = _DIR_ID_RE.match(name)
    if m and "_" in name:
        return name.split("_", 1)[1]
    return name


def _scan_script_episode_ids(project_dir: Path) -> list[str]:
    """扫描 剧本_E*.md，返回有逐集剧本的集 ID（按序号排序）。"""
    ids: list[str] = []
    for f in project_dir.glob("剧本_E*.md"):
        m = _SCRIPT_EP_RE.match(f.name)
        if m:
            ids.append(m.group(1))
    ids.sort(key=lambda e: int(e[1:]))
    return ids


def _build_episodes(
    project_dir: Path, script_index: Optional[dict]
) -> dict[str, EpisodeProgress]:
    """从 剧本.json 集索引 + 逐集文件，构建 episodes 进度索引。

    集 ID 来源：优先 剧本.json.episodes[].id，兜底扫描 剧本_E*.md。
    各集逐项产物路径：存在才填，便于 UI 据此判断断点。
    """
    episodes: dict[str, EpisodeProgress] = {}

    # 收集集 ID + 标题
    ep_titles: dict[str, str] = {}
    ordered_ids: list[str] = []
    if script_index and isinstance(script_index.get("episodes"), list):
        for entry in script_index["episodes"]:
            if isinstance(entry, dict) and entry.get("id"):
                eid = str(entry["id"])
                ep_titles[eid] = str(entry.get("title") or "")
                if eid not in ordered_ids:
                    ordered_ids.append(eid)
    # 兜底：剧本.json 缺集索引时扫文件
    if not ordered_ids:
        ordered_ids = _scan_script_episode_ids(project_dir)

    for eid in ordered_ids:
        ep = EpisodeProgress(title=ep_titles.get(eid, ""))

        script_p = _sw.script_episode_read_path(project_dir, eid)
        if script_p is not None:
            ep.script = script_p.name

        sb_p = _sw.storyboard_episode_read_path(project_dir, eid)
        if sb_p is not None:
            ep.storyboard = sb_p.name

        prompts_dir = _sw.episode_prompts_dir(project_dir, eid)
        if prompts_dir.is_dir():
            ep.image_prompts = f"prompts/{eid}/"

        episodes[eid] = ep

    return episodes


def _infer_pipeline(
    project_dir: Path,
    *,
    has_idea: bool,
    has_script: bool,
    has_storyboard: bool,
) -> dict[str, StageState]:
    """据既有产物推断四阶段状态机。

    - screenwriter：有剧本 → completed；仅有创意 → in_progress；都无 → pending。
    - storyboard：有分镜 → in_progress；否则 pending。
    - assets / production：暂按 pending（后续阶段接管）。
    """
    pipeline = {
        "screenwriter": StageState(),
        "assets": StageState(),
        "storyboard": StageState(),
        "production": StageState(),
    }

    if has_script:
        pipeline["screenwriter"] = StageState(
            state="completed", next_action="进入 ① 素材准备"
        )
    elif has_idea:
        pipeline["screenwriter"] = StageState(
            state="in_progress", next_action="继续完善剧本"
        )

    if has_storyboard:
        pipeline["storyboard"] = StageState(state="in_progress")

    return pipeline


def _build_artifacts(project_dir: Path) -> dict:
    """据存在的产物收口 artifacts 路径索引（不存在的不填）。"""
    artifacts: dict = {}

    idea_p = _sw.idea_read_path(project_dir)
    if idea_p is not None:
        artifacts["idea"] = idea_p.name

    script_index_p = _sw.script_index_path(project_dir)
    if script_index_p.is_file():
        artifacts["script_index"] = script_index_p.name

    # 各资源类 ref_index.json：存在才登记
    for kind in _cpaths.RESOURCE_KINDS:
        ref_p = _cpaths.ref_index_path(project_dir, kind)
        if ref_p.is_file():
            artifacts[kind] = f"{kind}/ref_index.json"

    return artifacts


def migrate_project_dir(
    project_dir, registry: Optional[ProjectRegistry] = None
) -> ProjectManifest:
    """把现有 project_dir 升级为带 project.json 的罗盘项目。

    幂等：已有 project.json → 原样加载返回，不覆盖、不重复登记。
    否则：扫描既有产物推断 pipeline / episodes / artifacts，生成 project.json，
    并（若传入 registry）登记进全局注册表。
    """
    project_dir = Path(project_dir)
    manifest_file = _cpaths.manifest_path(project_dir)

    # 幂等：已有 project.json → 不推倒重建
    if manifest_file.is_file():
        return load_manifest(manifest_file)

    # 扫描既有产物
    has_idea = _sw.idea_exists(project_dir)
    script_index_p = _sw.script_index_path(project_dir)
    script_index = _read_json(script_index_p) if script_index_p.is_file() else None
    has_script = script_index is not None or bool(_scan_script_episode_ids(project_dir))
    has_storyboard = any(project_dir.glob("分镜_E*.json")) or (
        project_dir / "分镜.json"
    ).is_file()

    # 身份
    project_id = _infer_project_id(project_dir)
    project_name = _infer_project_name(project_dir, script_index)

    manifest = ProjectManifest(
        project_id=project_id,
        project_name=project_name,
        pipeline=_infer_pipeline(
            project_dir,
            has_idea=has_idea,
            has_script=has_script,
            has_storyboard=has_storyboard,
        ),
        artifacts=_build_artifacts(project_dir),
        episodes=_build_episodes(project_dir, script_index),
    )

    save_manifest(manifest, manifest_file)

    # 登记进全局注册表（粗摘要）
    if registry is not None:
        registry.register(
            {
                "project_id": project_id,
                "project_name": project_name,
                "dir": project_dir.name + "/",
                "status": manifest.status,
                "episode_count": len(manifest.episodes),
            }
        )
        registry.save()

    return manifest
