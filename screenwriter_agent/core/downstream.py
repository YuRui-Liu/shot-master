"""下游产物清理——集感知。

阶段依赖链（v2）：
  ideate (创意.json)
  → script_outline (剧本.json)
  → script_episode (剧本_E{id}.md)
  → storyboard (分镜_E{id}.json)
  → prompts (prompts/E{id}/)
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from screenwriter_agent.core.paths import IDEA_FILE_NAME, IDEA_LEGACY_NAME

# 归档根目录名（项目根下）。换立意时旧下游产物整体移动到此，绝不删除。
ARCHIVE_DIR_NAME = "归档"

# 下游产物白名单（"当前生效立意"的产物）。归档/恢复都按这套规则搬运。
# 注意：不含 创意.json（立意本身常驻）、不含 imggen/video/soundtrack 大产物（默认不动）。
_DOWNSTREAM_FILE_NAMES = ("剧本.json", "剧本.md", "分镜.json")
_DOWNSTREAM_FILE_GLOBS = ("剧本_E*.md", "分镜_E*.json")
_DOWNSTREAM_DIR_NAMES = ("prompts", "video_prompts", "audio_prompts")


def safe_name(title: str, *, max_len: int = 40) -> str:
    """把立意标题转成安全的目录名片段：去非法字符、压空白、截断 ~40 字。"""
    s = (title or "").strip()
    # Windows/通用非法路径字符 + 控制字符 → 删
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", s)
    # 路径分隔/点开头等边界清理
    s = s.strip(" .")
    s = re.sub(r"\s+", " ", s)
    if len(s) > max_len:
        s = s[:max_len].rstrip(" .")
    return s or "untitled"


def _archive_root(project_dir: Path) -> Path:
    return project_dir / ARCHIVE_DIR_NAME


def _archive_dir_for(project_dir: Path, idea_id: str, title: str) -> Path:
    return _archive_root(project_dir) / f"{idea_id}__{safe_name(title)}"


def _find_archive_dir(project_dir: Path, idea_id: str) -> Path | None:
    """按 idea_id 前缀找现有归档目录（标题可能已改，仅靠 <idea_id>__ 前缀匹配）。"""
    root = _archive_root(project_dir)
    if not root.is_dir():
        return None
    prefix = f"{idea_id}__"
    for d in sorted(root.iterdir()):
        if d.is_dir() and d.name.startswith(prefix):
            return d
    return None


def _iter_downstream(project_dir: Path):
    """产出当前项目根下的下游产物路径（存在的）。"""
    for n in _DOWNSTREAM_FILE_NAMES:
        p = project_dir / n
        if p.is_file():
            yield p
    for pat in _DOWNSTREAM_FILE_GLOBS:
        for p in sorted(project_dir.glob(pat)):
            if p.is_file():
                yield p
    for n in _DOWNSTREAM_DIR_NAMES:
        p = project_dir / n
        if p.is_dir():
            yield p


def _move_into(src: Path, dst: Path) -> None:
    """把 src 移到 dst（dst 为目标完整路径）。dst 已存在则先腾挪（覆盖/并入）。

    - 文件：dst 存在先删，再 move。
    - 目录：逐项移入 dst（合并），同名项覆盖。
    """
    if src.is_dir():
        dst.mkdir(parents=True, exist_ok=True)
        for child in list(src.iterdir()):
            _move_into(child, dst / child.name)
        # 源目录搬空后删除
        try:
            src.rmdir()
        except OSError:
            pass
        return
    # 文件
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        if dst.is_dir():
            shutil.rmtree(dst, ignore_errors=True)
        else:
            try:
                dst.unlink()
            except OSError:
                pass
    shutil.move(str(src), str(dst))


def archive_downstream(project_dir: Path, idea_id: str, title: str) -> dict:
    """把当前项目根的下游白名单产物移动到 归档/<idea_id>__<safe_title>/。

    绝不删除——纯移动。目标目录已存在则并入/覆盖同名。
    返回 {"dir": "归档/<...>"|None, "files": [相对名...]}；无可归档产物时 dir=None。
    """
    project_dir = Path(project_dir)
    items = list(_iter_downstream(project_dir))
    if not items:
        return {"dir": None, "files": []}
    dest = _archive_dir_for(project_dir, idea_id, title)
    dest.mkdir(parents=True, exist_ok=True)
    moved: list[str] = []
    for src in items:
        rel = src.name + ("/" if src.is_dir() else "")
        _move_into(src, dest / src.name)
        moved.append(rel)
    return {"dir": f"{ARCHIVE_DIR_NAME}/{dest.name}", "files": moved}


def _parse_archive_dir_name(name: str) -> tuple[str, str]:
    """'c1__标题' → ('c1', '标题')；无 '__' 则整名当 idea_id、标题空。"""
    if "__" in name:
        idea_id, title = name.split("__", 1)
        return idea_id, title
    return name, ""


def list_archives(project_dir: Path) -> list[dict]:
    """扫 归档/ 目录列出所有归档立意（供 UI「往期立意」列表）。

    每条：{idea_id, title, dir, archived_at, file_count, is_active}。
    archived_at 取目录 mtime（ISO）；is_active 恒 False（归档区内即非生效）。
    """
    import time as _t

    project_dir = Path(project_dir)
    root = _archive_root(project_dir)
    out: list[dict] = []
    if not root.is_dir():
        return out
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        idea_id, title = _parse_archive_dir_name(d.name)
        try:
            file_count = sum(1 for _ in d.iterdir())
        except OSError:
            file_count = 0
        try:
            archived_at = _t.strftime(
                "%Y-%m-%dT%H:%M:%S", _t.localtime(d.stat().st_mtime))
        except OSError:
            archived_at = ""
        out.append({
            "idea_id": idea_id,
            "title": title,
            "dir": f"{ARCHIVE_DIR_NAME}/{d.name}",
            "archived_at": archived_at,
            "file_count": file_count,
            "is_active": False,
        })
    return out


def restore_downstream(project_dir: Path, idea_id: str) -> dict:
    """把 归档/<idea_id__*>/ 内的产物移回项目根（恢复编辑），并删空归档目录。

    返回 {"files": [相对名...]}；无该归档时 files=[]。
    """
    project_dir = Path(project_dir)
    src_dir = _find_archive_dir(project_dir, idea_id)
    if src_dir is None:
        return {"files": []}
    restored: list[str] = []
    for child in list(src_dir.iterdir()):
        rel = child.name + ("/" if child.is_dir() else "")
        _move_into(child, project_dir / child.name)
        restored.append(rel)
    # 归档目录搬空 → 删
    try:
        src_dir.rmdir()
    except OSError:
        pass
    return {"files": restored}


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
