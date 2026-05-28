"""模板加载（项目级覆盖优先 → 内置兜底）。

P1 不实现 user-scope；P3 加。
"""
from __future__ import annotations

from pathlib import Path

# 5 套内置模板的 id（spec §5.1）
BUILTIN_IDS = ("ideate", "script", "storyboard", "character_ref", "grid_prompt")

_BUILTIN_DIR = Path(__file__).resolve().parent.parent / "templates"


def load_template(tid: str, project_dir: Path) -> tuple[str, str]:
    """返回 (text, source)，source ∈ {'project', 'builtin'}。
    未知 id 抛 ValueError；内置缺失抛 FileNotFoundError。"""
    if tid not in BUILTIN_IDS:
        raise ValueError(f"未知模板 id: {tid}")
    # 1) 项目级覆盖
    proj = Path(project_dir) / ".agent" / "templates" / f"{tid}.md"
    if proj.is_file():
        return proj.read_text(encoding="utf-8"), "project"
    # 2) 内置
    builtin = _BUILTIN_DIR / f"{tid}.md"
    if not builtin.is_file():
        raise FileNotFoundError(f"内置模板缺失: {builtin}")
    return builtin.read_text(encoding="utf-8"), "builtin"
