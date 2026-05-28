"""扫描项目目录，按 4 阶段产物推断状态（spec §3.2）。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProjectState:
    project_dir: str
    name: str
    status: str = "empty"
    stages: dict[str, dict[str, Any]] = field(default_factory=dict)
    recommended_next: str = "ideate"
    config_overrides: dict[str, Any] = field(default_factory=dict)


_STAGE_ORDER = ("ideate", "script", "storyboard", "prompts")


def scan_project(project_dir: Path) -> ProjectState:
    """读项目目录，按 4 阶段产物推断状态。不验证文件内容合法性。"""
    project_dir = Path(project_dir).resolve()
    if not project_dir.is_dir():
        raise FileNotFoundError(str(project_dir))

    stages: dict[str, dict[str, Any]] = {}

    # ideate
    idea_path = project_dir / "idea.json"
    idea_file_exists = idea_path.is_file()
    if idea_file_exists:
        try:
            idea = json.loads(idea_path.read_text(encoding="utf-8"))
            selected = bool(idea.get("selected_id"))
            cand_count = len(idea.get("candidates", []))
            summary = (f"候选 {cand_count} 个，已选 {idea['selected_id']}"
                       if selected else f"候选 {cand_count} 个，未选定")
        except Exception:
            selected = False
            summary = "idea.json 解析失败"
        stages["ideate"] = {"done": selected, "file": "idea.json",
                            "_file_exists": True,
                            "summary": summary if selected else None}
    else:
        stages["ideate"] = {"done": False, "file": "idea.json",
                            "_file_exists": False, "summary": None}

    # script
    script_path = project_dir / "剧本.md"
    stages["script"] = {"done": script_path.is_file(), "file": "剧本.md",
                        "summary": _summarize_script(script_path)
                        if script_path.is_file() else None}

    # storyboard
    sb_path = project_dir / "分镜.json"
    stages["storyboard"] = {"done": sb_path.is_file(), "file": "分镜.json",
                            "summary": _summarize_storyboard(sb_path)
                            if sb_path.is_file() else None}

    # prompts
    prompts_dir = project_dir / "prompts"
    has_prompts = prompts_dir.is_dir() and any(prompts_dir.iterdir())
    stages["prompts"] = {"done": has_prompts, "subdir": "prompts/",
                         "summary": f"{len(list(prompts_dir.iterdir()))} 个文件"
                         if has_prompts else None}

    # 推导项目级 status + recommended_next
    status, nxt = _derive_status(stages)

    return ProjectState(
        project_dir=str(project_dir),
        name=project_dir.name,
        status=status,
        stages=stages,
        recommended_next=nxt,
    )


def _derive_status(stages: dict) -> tuple[str, str]:
    """spec §3.2 表。

    "empty"    — idea.json 不存在且所有阶段均未完成
    "ideating" — idea.json 存在但尚未选定方案
    以此类推……
    """
    done = {k: bool(v["done"]) for k, v in stages.items()}
    idea_file_exists = stages["ideate"].get("_file_exists", False)
    # 真正的 empty：idea.json 都不存在，其他阶段也全空
    if not idea_file_exists and not any(done.values()):
        return "empty", "ideate"
    if not done["ideate"]:
        return "ideating", "ideate"
    if not done["script"]:
        return "script_pending", "script"
    if not done["storyboard"]:
        return "storyboard_pending", "storyboard"
    if not done["prompts"]:
        return "prompts_pending", "prompts"
    return "done", "prompts"


def _summarize_script(p: Path) -> str | None:
    try:
        lines = p.read_text(encoding="utf-8").splitlines()[:30]
        for ln in lines:
            ln = ln.strip()
            if ln.startswith("标题") and "：" in ln:
                return ln.split("：", 1)[1].strip()
            if ln.startswith("标题:"):
                return ln.split(":", 1)[1].strip()
    except Exception:
        pass
    return None


def _summarize_storyboard(p: Path) -> str | None:
    try:
        sb = json.loads(p.read_text(encoding="utf-8"))
        n = len(sb.get("shots", []))
        return f"{n} 个镜头 · {sb.get('totalDuration', '?')}s"
    except Exception:
        return None
