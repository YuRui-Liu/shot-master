"""模板加载/渲染/推荐。

模板格式 = YAML frontmatter（--- ... ---） + 正文（jinja-like `{{var}}` 占位符）。
没引 jinja，避免大依赖；占位符替换用简单字符串替换即可。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


VAR_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


@dataclass
class TemplateVariable:
    name: str
    type: str = "text"           # int / float / text / textarea / select / file_pick
    default: Any = None
    label: str = ""
    required: bool = False
    optional: bool = False
    options: list[str] = field(default_factory=list)  # for select
    placeholder: str = ""


@dataclass
class Template:
    id: str                       # 文件名去 .md 后缀
    name: str
    body: str
    path: Path
    suggest_when: str = ""        # 条件表达式（image_count, has_script 等）
    variables: list[TemplateVariable] = field(default_factory=list)


def load_template(path: Path) -> Template:
    raw = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(raw)
    if not m:
        # 无 frontmatter：当作纯正文
        return Template(id=path.stem, name=path.stem, body=raw, path=path)
    meta_yaml, body = m.group(1), m.group(2)
    meta = yaml.safe_load(meta_yaml) or {}
    variables = []
    for v in meta.get("variables", []) or []:
        variables.append(TemplateVariable(
            name=v["name"],
            type=v.get("type", "text"),
            default=v.get("default"),
            label=v.get("label", v["name"]),
            required=bool(v.get("required", False)),
            optional=bool(v.get("optional", False)),
            options=v.get("options", []) or [],
            placeholder=v.get("placeholder", ""),
        ))
    return Template(
        id=path.stem,
        name=meta.get("name", path.stem),
        body=body,
        path=path,
        suggest_when=meta.get("suggest_when", ""),
        variables=variables,
    )


def list_templates(directory: Path) -> list[Template]:
    if not directory.exists():
        return []
    return [load_template(p) for p in sorted(directory.glob("*.md"))]


def render_template(tpl: Template, values: dict[str, Any]) -> str:
    """把 {{var}} 替换为 values 中的值；缺失走 default；required 缺失则报错。"""
    resolved: dict[str, Any] = {}
    for var in tpl.variables:
        if var.name in values and values[var.name] not in (None, ""):
            resolved[var.name] = values[var.name]
        elif var.default is not None:
            resolved[var.name] = var.default
        elif var.required and not var.optional:
            raise ValueError(f"required variable missing: {var.name}")
        else:
            resolved[var.name] = ""

    def _sub(match: re.Match) -> str:
        name = match.group(1)
        return str(resolved.get(name, ""))

    return VAR_PATTERN.sub(_sub, tpl.body)


def recommend_template(templates: list[Template],
                       image_count: int,
                       has_script: bool = False) -> Optional[Template]:
    """按 suggest_when 表达式找第一个匹配的模板。

    支持的简易表达式语法：image_count == N / image_count >= N / image_count <= N /
    image_count > N / image_count < N，以及 'has_script'。
    """
    ctx = {"image_count": image_count, "has_script": has_script}
    for tpl in templates:
        if not tpl.suggest_when:
            continue
        expr = tpl.suggest_when.strip()
        try:
            # 仅允许识别变量名 + 比较符 + 数字
            if eval(expr, {"__builtins__": {}}, ctx):
                return tpl
        except Exception:
            continue
    return None
