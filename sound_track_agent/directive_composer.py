"""对话式配乐方向归并：用文本 LLM 把多轮对话 + 新指令归并成结构化方向。

provider 复用 OpenAICompatProvider.generate(images, system_prompt, user_supplement)，
传 images=[] 即纯文本对话。不联网生成音频。
"""
from __future__ import annotations

import json
import re

from sound_track_agent.session import SoundtrackDirective

_SYSTEM = (
    "你是短剧配乐方向助手。根据「当前全局方向 + 历史对话 + 用户新指令」，"
    "归并出更新后的配乐方向。新指令若是修正/覆盖（如把『舒缓』改成『快』），"
    "必须覆盖旧设定而非简单叠加。\n"
    "只输出一个 JSON 对象，不要多余文字，格式：\n"
    '{"global": "整体配乐方向（风格/情绪曲线/乐器/速度）", '
    '"segments": {"段序号": "该段方向"}, "reply": "一句给用户的变更摘要"}\n'
    "segments 可为空对象 {}。"
)


def _parse_json(raw: str):
    """容错解析：直接 loads；失败则抽取第一个 {...} 再 loads；再失败返回 None。"""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        pass
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def synthesize_directive(provider, current: SoundtrackDirective,
                         instruction: str, n_segments: int) -> SoundtrackDirective:
    convo = "\n".join(f"{m.get('role')}: {m.get('text')}"
                      for m in current.conversation)
    user = (
        f"当前全局方向：{current.global_directive or '（空）'}\n"
        f"历史对话：\n{convo or '（无）'}\n"
        f"视频共 {n_segments} 段。\n"
        f"用户新指令：{instruction}"
    )
    try:
        raw = provider.generate([], _SYSTEM, user)
    except Exception:
        parsed = None
    else:
        parsed = _parse_json(raw)

    if parsed is None:
        new_global = current.global_directive
        new_segs = dict(current.segment_directives)
        reply = "AI 返回无法解析，配乐方向保持不变，请换个说法重述。"
    else:
        new_global = parsed.get("global") or current.global_directive
        new_segs = {}
        for k, v in (parsed.get("segments") or {}).items():
            try:
                new_segs[int(k)] = v
            except (TypeError, ValueError):
                continue
        if not new_segs:
            new_segs = dict(current.segment_directives)
        reply = parsed.get("reply") or "已更新配乐方向。"

    conversation = list(current.conversation) + [
        {"role": "user", "text": instruction},
        {"role": "assistant", "text": reply},
    ]
    return SoundtrackDirective(global_directive=new_global,
                               segment_directives=new_segs,
                               conversation=conversation)
