"""模板加载（三级优先：project > global > builtin）。

global 层路径：~/.config/shot-drama/templates/<tid>.md（POSIX/Win 通用）
"""
from __future__ import annotations

from pathlib import Path

from screenwriter_agent.core.atomic_write import atomic_write_text

# 5 套内置模板的 id
BUILTIN_IDS = ("ideate", "script", "storyboard", "character_ref", "grid_prompt")

# 内置模板目录（.md 文件与本文件同目录）
_BUILTIN_DIR = Path(__file__).resolve().parent

# 全局覆盖目录（可在测试中 monkeypatch）
GLOBAL_TEMPLATE_DIR = Path.home() / ".config" / "shot-drama" / "templates"


def global_template_path(tid: str) -> Path:
    """返回 tid 对应的全局覆盖路径（不保证存在）。"""
    if tid not in BUILTIN_IDS:
        raise ValueError(f"未知模板 id: {tid!r}，合法值：{BUILTIN_IDS}")
    return GLOBAL_TEMPLATE_DIR / f"{tid}.md"


def write_global_template(tid: str, text: str) -> None:
    """写入全局覆盖模板；空 text 视为删除（回退 builtin）。"""
    if tid not in BUILTIN_IDS:
        raise ValueError(f"未知模板 id: {tid!r}，合法值：{BUILTIN_IDS}")
    p = GLOBAL_TEMPLATE_DIR / f"{tid}.md"
    if text == "":
        # 删除：如果文件存在则移除
        if p.is_file():
            p.unlink()
        return
    atomic_write_text(p, text)


def load_template(tid: str, project_dir=None) -> tuple[str, str]:
    """返回 (text, source)，source ∈ {'project', 'global', 'builtin'}。

    优先级：project > global > builtin。
    未知 id 抛 ValueError；内置缺失抛 FileNotFoundError。
    project_dir 为 None 时跳过 project 层。
    """
    if tid not in BUILTIN_IDS:
        raise ValueError(f"未知模板 id: {tid!r}，合法值：{BUILTIN_IDS}")

    # 1) 项目级覆盖
    if project_dir is not None:
        proj = Path(project_dir) / ".agent" / "templates" / f"{tid}.md"
        if proj.is_file():
            return proj.read_text(encoding="utf-8"), "project"

    # 2) 全局覆盖
    glob = GLOBAL_TEMPLATE_DIR / f"{tid}.md"
    if glob.is_file():
        return glob.read_text(encoding="utf-8"), "global"

    # 3) 内置
    builtin = _BUILTIN_DIR / f"{tid}.md"
    if not builtin.is_file():
        raise FileNotFoundError(f"内置模板缺失: {builtin}")
    return builtin.read_text(encoding="utf-8"), "builtin"
