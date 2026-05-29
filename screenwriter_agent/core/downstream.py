"""下游产物清理——集感知。

阶段依赖链（v2）：
  ideate (创意.json)
  → script_outline (剧本.json)
  → script_episode (剧本_E{id}.md)
  → storyboard (分镜_E{id}.json)
  → prompts (prompts/E{id}/)
"""
from __future__ import annotations

import shutil
from pathlib import Path

from screenwriter_agent.core.paths import IDEA_FILE_NAME, IDEA_LEGACY_NAME


def _rm_file(p: Path) -> bool:
    try:
        if p.is_file():
            p.unlink()
            return True
    except OSError:
        pass
    return False


def _rm_dir(p: Path) -> bool:
    try:
        if p.is_dir():
            shutil.rmtree(p)
            return True
    except OSError:
        pass
    return False


def _all_episode_ids(project_dir: Path) -> list[str]:
    """从 剧本_E*.md 文件名扫所有集 id（含旧 剧本.md → E1）。"""
    ids: list[str] = []
    for f in project_dir.glob("剧本_E*.md"):
        stem = f.stem  # "剧本_E1"
        if "_" in stem:
            ep = stem.split("_", 1)[1]
            if ep.startswith("E") and ep[1:].isdigit():
                ids.append(ep)
    if not ids and (project_dir / "剧本.md").is_file():
        ids.append("E1")
    return ids


def purge_downstream(project_dir: Path, *, stage: str,
                      episode_id: str | None = None) -> list[str]:
    """按 stage [+ episode_id] 删本阶段及下游产物。返回被删的相对路径（调试用）。

    stage:
        'ideate' / 'script_outline' / 'script_episode' / 'storyboard' / 'prompts'
    """
    removed: list[str] = []

    if stage == "ideate":
        for n in (IDEA_FILE_NAME, IDEA_LEGACY_NAME):
            if _rm_file(project_dir / n):
                removed.append(n)
        _purge_all_script_and_below(project_dir, removed)
        return removed

    if stage == "script_outline":
        _purge_all_script_and_below(project_dir, removed)
        return removed

    if stage == "script_episode":
        if episode_id is None:
            _purge_all_script_and_below(project_dir, removed)
            return removed
        for rel in (f"剧本_{episode_id}.md",
                     f"分镜_{episode_id}.json"):
            if _rm_file(project_dir / rel):
                removed.append(rel)
        if _rm_dir(project_dir / "prompts" / episode_id):
            removed.append(f"prompts/{episode_id}/")
        return removed

    if stage == "storyboard":
        if episode_id is None:
            for f in project_dir.glob("分镜_E*.json"):
                if _rm_file(f):
                    removed.append(f.name)
            if _rm_file(project_dir / "分镜.json"):
                removed.append("分镜.json")
            if _rm_dir(project_dir / "prompts"):
                removed.append("prompts/")
            return removed
        if _rm_file(project_dir / f"分镜_{episode_id}.json"):
            removed.append(f"分镜_{episode_id}.json")
        if _rm_dir(project_dir / "prompts" / episode_id):
            removed.append(f"prompts/{episode_id}/")
        return removed

    if stage == "prompts":
        if episode_id is None:
            if _rm_dir(project_dir / "prompts"):
                removed.append("prompts/")
            return removed
        if _rm_dir(project_dir / "prompts" / episode_id):
            removed.append(f"prompts/{episode_id}/")
        return removed

    return removed


def _purge_all_script_and_below(project_dir: Path, removed: list[str]) -> None:
    """清 剧本.json + 所有 剧本_E*.md + 旧 剧本.md + 所有分镜/prompts。"""
    if _rm_file(project_dir / "剧本.json"):
        removed.append("剧本.json")
    if _rm_file(project_dir / "剧本.md"):
        removed.append("剧本.md")
    for f in project_dir.glob("剧本_E*.md"):
        if _rm_file(f):
            removed.append(f.name)
    for f in project_dir.glob("分镜_E*.json"):
        if _rm_file(f):
            removed.append(f.name)
    if _rm_file(project_dir / "分镜.json"):
        removed.append("分镜.json")
    if _rm_dir(project_dir / "prompts"):
        removed.append("prompts/")
    if _rm_dir(project_dir / "video_prompts"):
        removed.append("video_prompts/")
    if _rm_dir(project_dir / "audio_prompts"):
        removed.append("audio_prompts/")
