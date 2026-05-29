"""下游产物清理——重生时按 stage 删本阶段+所有下游产物。

阶段依赖链：ideate (创意.json) → script (剧本.md) → storyboard (分镜.json) → prompts (prompts/)
某阶段重生时，清掉它自己 + 所有下游。
"""
from __future__ import annotations

import shutil
from pathlib import Path

from screenwriter_agent.core.paths import IDEA_FILE_NAME, IDEA_LEGACY_NAME


def purge_downstream(project_dir: Path, *, stage: str) -> list[str]:
    """根据 stage 删本阶段及所有下游产物。返回被删的相对路径列表（调试用）。

    stage 取值：'script' | 'storyboard' | 'prompts'
    （'ideate' 不调本函数；ideate 重生直接覆盖 创意.json）
    """
    removed: list[str] = []

    def _rm_file(rel: str) -> None:
        p = project_dir / rel
        try:
            if p.is_file():
                p.unlink()
                removed.append(rel)
        except OSError:
            pass

    def _rm_dir(rel: str) -> None:
        p = project_dir / rel
        try:
            if p.is_dir():
                shutil.rmtree(p)
                removed.append(rel + "/")
        except OSError:
            pass

    # 本阶段产物 + 下游
    if stage == "script":
        _rm_file("剧本.md")
        _rm_file("分镜.json")
        _rm_dir("prompts")
    elif stage == "storyboard":
        _rm_file("分镜.json")
        _rm_dir("prompts")
    elif stage == "prompts":
        _rm_dir("prompts")
    # ideate 重生只是 atomic_write 覆盖 创意.json + 删下游
    elif stage == "ideate":
        _rm_file(IDEA_FILE_NAME)
        _rm_file(IDEA_LEGACY_NAME)
        _rm_file("剧本.md")
        _rm_file("分镜.json")
        _rm_dir("prompts")
    return removed
