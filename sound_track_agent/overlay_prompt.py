"""框选生成对话框的 prompt 预填：调一次 LLM 给生成提示词建议。

输入：kind（bgm/sfx）、框选区间内对白字幕、段落 global_style 上下文。
复用配乐 vision provider（纯文本进出，images=[]）。

降级原则：未配置 / provider 构造或调用抛 / 返回空 → 一律返回 ""，
让对话框留空由用户手填，绝不崩。纯逻辑无 Qt，可全 mock 单测。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from sound_track_agent.provider import build_soundtrack_provider

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "你是影视配乐/音效提示词助手。根据给定的画面区间信息，"
    "为指定类型的音频片段生成一句简洁、可直接用于生成模型的英文/中文风格描述。"
    "只输出提示词本身，不要解释、不要引号、不要前后缀。"
)


def _load_global_style(work_dir) -> str:
    """从 work_dir/session.json 读 global_style；缺失/损坏 → ""。"""
    try:
        p = Path(work_dir) / "session.json"
        if not p.is_file():
            return ""
        d = json.loads(p.read_text(encoding="utf-8"))
        return str(d.get("global_style", "") or "")
    except Exception:
        return ""


def _build_user_message(kind: str, t_start: float, t_end: float,
                        dialogue_text: str, global_style: str) -> str:
    """把 kind / 区间 / 对白字幕 / 整体风格拼成模型输入。"""
    kind_cn = "背景音乐(BGM)" if kind == "bgm" else "音效(SFX)"
    lines = [
        f"音频类型：{kind} （{kind_cn}）",
        f"区间：{t_start:.2f}s - {t_end:.2f}s（时长 {t_end - t_start:.2f}s）",
    ]
    if global_style:
        lines.append(f"整体风格 global_style：{global_style}")
    if dialogue_text:
        lines.append(f"区间内对白字幕：{dialogue_text}")
    lines.append("请给出一句生成提示词：")
    return "\n".join(lines)


def suggest_overlay_prompt(kind: str, t_start: float, t_end: float, *,
                           work_dir, cfg, dialogue_text: str = "") -> str:
    """用现有 LLM provider 给一句生成提示词建议。

    失败/未配置/超时/返回空 → 返回 ""（降级，不抛）。
    """
    try:
        global_style = _load_global_style(work_dir)
        provider = build_soundtrack_provider(cfg)
        user_msg = _build_user_message(
            kind, float(t_start), float(t_end), dialogue_text, global_style)
        raw = provider.generate([], _SYSTEM_PROMPT, user_msg)
        return (raw or "").strip()
    except Exception as e:   # noqa: BLE001 全降级
        log.debug("suggest_overlay_prompt 降级（返回空）：%s", e)
        return ""
