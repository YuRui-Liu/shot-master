"""把 ParsedResult 写为 md + json。

md: 给人看的，含原始 vision 输出 + 解析后的字段块；适合后续手工微调。
json: 给 ComfyUI 工作流读的，纯结构化数据。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.core.result_parser import ParsedResult


def resolve_output_dir(image_path: Optional[Path],
                       default_output_dir: Optional[str]) -> Path:
    """决定输出目录。
    - 优先用 default_output_dir（来自 .env 或显式参数）
    - 否则输出到 image_path 同级的 _prompts/
    """
    if default_output_dir:
        return Path(default_output_dir)
    if image_path is None:
        return Path("output")
    return image_path.parent / "_prompts"


def write_outputs(result: ParsedResult,
                  output_dir: Path,
                  base_name: str,
                  template_id: str,
                  provider: str,
                  model: str) -> tuple[Path, Path]:
    """写 base_name.md 和 base_name.json 到 output_dir。返回 (md_path, json_path)。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / f"{base_name}.md"
    json_path = output_dir / f"{base_name}.json"

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    md_lines = [
        f"# {base_name} · 反推提示词",
        "",
        f"- 模板：`{template_id}`",
        f"- 后端：`{provider}` / 模型：`{model}`",
        f"- 生成时间：{ts}",
        "",
        "## global_prompt",
        "```",
        result.global_prompt,
        "```",
        "",
        "## timeline_data",
        "```json",
        result.timeline_data,
        "```",
        "",
        "## local_prompts",
        "```",
        result.local_prompts,
        "```",
        "",
        "## segment_lengths",
        "```",
        ", ".join(str(x) for x in result.segment_lengths),
        "```",
        "",
        "## max_frames",
        "```",
        str(result.max_frames) if result.max_frames is not None else "",
        "```",
        "",
        "## frame_indices",
        "```",
        "\n".join(f"frame_idx_{i+1} = {v}" for i, v in enumerate(result.frame_indices)),
        "```",
        "",
        "## strengths",
        "```",
        "\n".join(f"strength_{i+1} = {v}" for i, v in enumerate(result.strengths)),
        "```",
        "",
        "## epsilon",
        "```",
        str(result.epsilon) if result.epsilon is not None else "",
        "```",
        "",
        "## notes",
        result.notes,
        "",
        "---",
        "",
        "## 原始模型输出",
        "```",
        result.raw,
        "```",
    ]
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    data = {
        "global_prompt": result.global_prompt,
        "timeline_data": result.timeline_data,
        "local_prompts": result.local_prompts,
        "segment_lengths": result.segment_lengths,
        "max_frames": result.max_frames,
        "frame_indices": result.frame_indices,
        "strengths": result.strengths,
        "epsilon": result.epsilon,
        "notes": result.notes,
        "meta": {
            "base_name": base_name,
            "template_id": template_id,
            "provider": provider,
            "model": model,
            "generated_at": ts,
        },
    }
    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    return md_path, json_path
