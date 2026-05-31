"""风格圣经三段式：全局风格库 + 渲染注入逻辑（Qt-free 纯逻辑）。

研究依据 §4.1（全局库 schema）/ §4.3（三层注入 + 指纹分层护栏）：

- **全局库**：`templates/styles/visual_styles.json`，按 真人(real)/2D/3D 三类
  收录 seed 风格，每条含 `style_id` / `category` / `name_cn` / `source` /
  摄影或 2D/3D 参数 / `prompt_suffix` / `ref_fingerprint` / `negative_suffix`，
  顶层带 `default_style_id`。
- **项目引用**：项目只存 `style_id`，渲染时按 ID 解析实体（见 get_style）。
- **渲染注入**（inject_style_prompt）：
    stage="ref"    → 出 ref 图阶段 append `ref_fingerprint`（中性平光锁一致性）。
    stage="render" → 分镜/出片阶段 **不** append fingerprint，否则中性平光
                     污染戏剧打光（OnlyShot 失败模式 16 / `--no-fingerprint`）。
    两个阶段都 append `prompt_suffix`，并以 `negative_suffix`（禁字幕常量句，
    Yvonne 收尾护栏）收尾。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

# 全局风格库默认路径：drama_shot_master/templates/styles/visual_styles.json
_DEFAULT_STYLES_PATH = (
    Path(__file__).resolve().parent.parent / "templates" / "styles" / "visual_styles.json"
)


def load_styles(path: str | Path | None = None) -> dict:
    """加载全局风格库，返回原始 dict（含 schema_version/default_style_id/styles）。

    path=None 时读内置默认库；传入路径则读用户级/自定义库。
    """
    p = Path(path) if path is not None else _DEFAULT_STYLES_PATH
    with p.open("r", encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=None)
def _default_index() -> dict:
    """内置默认库的 style_id → style 索引（缓存，避免重复读盘）。"""
    data = load_styles()
    return {s["style_id"]: s for s in data.get("styles", [])}


def get_style(style_id: str, path: str | Path | None = None) -> Optional[dict]:
    """按 style_id 解析风格实体；缺失安全返回 None。

    path=None 走缓存的内置库；传入路径则即时读取该库（不缓存）。
    """
    if path is None:
        return _default_index().get(style_id)
    data = load_styles(path)
    for s in data.get("styles", []):
        if s.get("style_id") == style_id:
            return s
    return None


def inject_style_prompt(base_prompt: str, style: dict, *, stage: str = "render") -> str:
    """把风格注入分镜底图 prompt，按阶段决定是否加视觉指纹。

    拼装顺序：base_prompt → [ref_fingerprint(仅 ref 阶段)] → prompt_suffix
              → negative_suffix（恒在，收尾）。

    - stage="ref"：append `ref_fingerprint`（中性平光锁一致性）。
    - stage="render"（默认）：**不** append fingerprint，避免中性平光污染戏剧打光。
    """
    parts: list[str] = [base_prompt.strip()] if base_prompt.strip() else []

    if stage == "ref":
        fp = (style.get("ref_fingerprint") or "").strip()
        if fp:
            parts.append(fp)

    suffix = (style.get("prompt_suffix") or "").strip()
    if suffix:
        parts.append(suffix)

    # 收尾护栏：禁字幕常量句恒在，且置于末尾
    neg = (style.get("negative_suffix") or "").strip()
    if neg:
        parts.append(neg)

    return ", ".join(parts)
