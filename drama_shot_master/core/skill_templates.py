"""创作技能 loader（纯逻辑，无 Qt，全单测）。

镜像 core/genre_templates.py 的写法：扫描 templates/skills/creations/*.md 的
YAML front-matter，作为本项目第三类可加载资产（与 genres / styles 并列）。
设计依据：docs/explorer/skills-loader-design.md。

对外接口：
- list_skills()            -> list[dict]   全部 SkillManifest（前端网格/筛选直接消费）
- load_skill(skill_id)     -> dict         单个 SkillManifest（含正文 body_md）
- validate_skill(manifest) -> (ok, errors) front-matter 必填校验

设计要点（镜像 genre_templates）：
- 定位：core/ -> drama_shot_master/，模板随包分发（templates/skills/creations/*.md）。
- 解析：每个 .md = YAML front-matter（--- 包裹）+ 正文知识库。只读 front-matter 决定
  卡片展示与注入；正文按需作为 prompt 注入素材。
- 容错（设计 §3）：front-matter 缺失/解析失败时回退——name 取文件名（去序号前缀/扩展名），
  cat/medium 缺省「通用」，modules 缺省空列表；解析失败不阻断其他技能加载。
"""
from __future__ import annotations

from pathlib import Path
from typing import Tuple

import yaml

# core/ -> drama_shot_master/；模板随包分发（drama_shot_master/templates 被 build spec 打包）
_PKG_ROOT = Path(__file__).resolve().parents[1]
_SKILLS_DIR = _PKG_ROOT / "templates" / "skills"
_CREATIONS_DIR = _SKILLS_DIR / "creations"

# 分类 / 阶段枚举（集中维护，前后端共享，设计 §7 避免漂移）
CATS = ("短剧", "MV", "广告/TVC", "纪录/人文", "动画", "口播/解说",
        "直播/转播", "互动/POV", "工具/素材", "通用")
STAGES = ("剧本", "分镜prompt", "生视频", "风格", "配乐", "配音", "成片")
PRIORITIES = ("high", "mid", "low")

# front-matter 必填字段（其余可缺省回退）
_REQUIRED_FIELDS = ("id", "name", "cat", "medium", "desc")


def _strip_seq_prefix(stem: str) -> str:
    """去掉文件名序号前缀（如 '09-AI短剧一站式生成' -> 'AI短剧一站式生成'）。"""
    s = stem.strip()
    if "-" in s:
        head, _, tail = s.partition("-")
        if head.isdigit() and tail:
            return tail.strip()
    return s


def _parse_front_matter(text: str) -> Tuple[dict, str]:
    """从 .md 文本拆出 (front_matter_dict, body_md)。

    front-matter 用 `---` 包裹于文件开头。缺失/解析失败时返回 ({}, 原文)。
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    # 找闭合的 ---
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm_text = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1:]).lstrip("\n")
            try:
                fm = yaml.safe_load(fm_text)
            except yaml.YAMLError:
                return {}, text
            if not isinstance(fm, dict):
                return {}, text
            return fm, body
    return {}, text


def _normalize_modules(raw) -> list:
    """把 front-matter 的 modules 规整为 [{id,stage,priority}]。

    兼容两种写法：dict 列表（设计 §3 主写法）与 [name,stage,priority] 三元组列表
    （web/skills.html mockup 写法）。容错：缺省空列表。
    """
    if not isinstance(raw, (list, tuple)):
        return []
    out = []
    for item in raw:
        if isinstance(item, dict):
            mid = str(item.get("id", "")).strip()
            stage = str(item.get("stage", "")).strip()
            prio = str(item.get("priority", "mid")).strip() or "mid"
            if mid or stage:
                out.append({"id": mid, "stage": stage, "priority": prio})
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            mid = str(item[0]).strip()
            stage = str(item[1]).strip()
            prio = str(item[2]).strip() if len(item) >= 3 else "mid"
            out.append({"id": mid, "stage": stage, "priority": prio or "mid"})
    return out


def _build_manifest(path: Path) -> dict:
    """读单个 .md → SkillManifest dict（含容错回退）。"""
    text = path.read_text(encoding="utf-8")
    fm, body = _parse_front_matter(text)
    fallback_name = _strip_seq_prefix(path.stem)
    skill_id = str(fm.get("id") or fallback_name).strip()
    return {
        "id": skill_id,
        "name": str(fm.get("name") or fallback_name).strip(),
        "cat": str(fm.get("cat") or "通用").strip(),
        "medium": str(fm.get("medium") or "通用").strip(),
        "icon": str(fm.get("icon") or "").strip(),
        "desc": str(fm.get("desc") or "").strip(),
        "output": str(fm.get("output") or "").strip(),
        "modules": _normalize_modules(fm.get("modules")),
        "style_hint": (str(fm["style_hint"]).strip()
                       if fm.get("style_hint") else None),
        "prompt_template": (str(fm["prompt_template"])
                            if fm.get("prompt_template") else None),
        "body_md": body,
        "source_path": str(path),
    }


def list_skills() -> list:
    """扫描 creations/*.md，返回全部 SkillManifest（按 id 排序）。

    单个文件解析失败不阻断其他技能（设计 §3 容错），跳过该文件。
    目录缺失时返回空列表。
    """
    if not _CREATIONS_DIR.is_dir():
        return []
    manifests = []
    for path in sorted(_CREATIONS_DIR.glob("*.md")):
        try:
            manifests.append(_build_manifest(path))
        except (OSError, UnicodeDecodeError):
            continue
    manifests.sort(key=lambda m: m["id"])
    return manifests


def load_skill(skill_id: str) -> dict:
    """加载单个技能 SkillManifest（含正文 body_md）。

    先按 front-matter id 匹配，回退按文件名匹配。未找到抛 FileNotFoundError。
    """
    if not _CREATIONS_DIR.is_dir():
        raise FileNotFoundError(f"技能目录不存在: {_CREATIONS_DIR}")
    target = skill_id.strip()
    for path in sorted(_CREATIONS_DIR.glob("*.md")):
        try:
            manifest = _build_manifest(path)
        except (OSError, UnicodeDecodeError):
            continue
        if manifest["id"] == target or path.stem == target:
            return manifest
    raise FileNotFoundError(f"创作技能不存在: {skill_id}")


def validate_skill(manifest: dict) -> Tuple[bool, list]:
    """校验技能 manifest：front-matter 必填 + 枚举合法性。

    返回 (ok, errors)；ok 为 True 当且仅当 errors 为空。
    """
    errors: list = []
    if not isinstance(manifest, dict):
        return False, ["manifest 不是 dict"]

    for key in _REQUIRED_FIELDS:
        val = manifest.get(key)
        if val is None or (isinstance(val, str) and not val.strip()):
            errors.append(f"缺字段或为空: {key}")

    cat = manifest.get("cat")
    if cat and cat not in CATS:
        errors.append(f"cat 非法枚举: {cat!r}")

    mods = manifest.get("modules")
    if mods is not None:
        if not isinstance(mods, list):
            errors.append("modules 须为列表")
        else:
            for i, m in enumerate(mods):
                if not isinstance(m, dict):
                    errors.append(f"modules[{i}] 须为映射")
                    continue
                if not str(m.get("id", "")).strip() and \
                        not str(m.get("stage", "")).strip():
                    errors.append(f"modules[{i}] 缺 id/stage")
                prio = m.get("priority")
                if prio and prio not in PRIORITIES:
                    errors.append(f"modules[{i}].priority 非法: {prio!r}")
                stage = m.get("stage")
                if stage and stage not in STAGES:
                    errors.append(f"modules[{i}].stage 非法枚举: {stage!r}")

    return (len(errors) == 0), errors
