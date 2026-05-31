"""注入装配纯函数（②a，无 Qt / 无网络）：题材模板 + 风格圣经 → 各生成阶段注入文本。

架构决策 A（客户端组装解耦）：主包侧读 load_genre/get_style 组装好**纯文本**，
经 request 字段传给 screenwriter_agent；screenwriter_agent 不反向依赖主包。

四个对外接口（照 spec「注入契约」/ 研究 §3 §4 §5）：
- build_genre_context  题材模板 → script/storyboard 阶段注入文本（OnlyShot 共用骨架）
- build_style_context  风格圣经 → 复用 style_bible.inject_style_prompt（指纹分层）
- build_video_director_prompts  storyboard → 导演台视频结构（LTX 2.3）
- guard_prompt  失败模式 guardrail（OnlyShot 失败模式 1/2：禁词替换 + 限长）
"""
from __future__ import annotations

from .style_bible import inject_style_prompt

# storyboard Shot.duration 缺省值（对齐 screenwriter_agent/models/storyboard_schema.py）
_DEFAULT_DURATION = 3.0

# 失败模式 guardrail：内容审核禁词替换表（研究 § 失败模式 2）。
# 顺序敏感——较长短语在前，避免被短词先替换破坏。
_BANNED_REPLACEMENTS = (
    ("extreme close-up", "medium shot"),
    ("sinister", "moody"),
    ("blush", "rose tint"),
)


def build_genre_context(genre_dict: dict) -> str:
    """题材模板 → 注入文本（用于 script/storyboard 阶段 prompt）。

    组装 OnlyShot 共用骨架（研究 §3）：
      §0 hard_constraints（非空则 ⚠️ 置顶）
      §1 identity（一句话 one_liner / 受众 audience / 冲突源 conflict_source）
      §2 rhythm（秒锚点 open_3s/open_30s + 爆点密度 beat_density）
      §3 satisfaction_weights（爽点类型 %，0xsline 爽点矩阵）
      §4 writing_rules（do）
      §5 donts（don't）

    空 dict → 空串。
    """
    if not genre_dict:
        return ""

    sections: list[str] = []

    # §0 硬约束（⚠️ 置顶，仅高风险题材填）
    hard = genre_dict.get("hard_constraints") or []
    if hard:
        lines = ["## ⚠️ 硬约束（最高优先级，违反即废）"]
        lines += [f"- {item}" for item in hard]
        sections.append("\n".join(lines))

    # §1 特征
    identity = genre_dict.get("identity") or {}
    if identity:
        lines = ["## 题材特征"]
        if identity.get("one_liner"):
            lines.append(f"- 一句话定位：{identity['one_liner']}")
        if identity.get("audience"):
            lines.append(f"- 目标受众：{identity['audience']}")
        conflict = identity.get("conflict_source")
        if conflict:
            lines.append(f"- 冲突源：{_join(conflict)}")
        sections.append("\n".join(lines))

    # §2 节奏
    rhythm = genre_dict.get("rhythm") or {}
    if rhythm:
        lines = ["## 节奏"]
        if rhythm.get("open_3s"):
            lines.append(f"- 黄金 3 秒：{rhythm['open_3s']}")
        if rhythm.get("open_30s"):
            lines.append(f"- 前 30 秒：{rhythm['open_30s']}")
        if rhythm.get("beat_density"):
            lines.append(f"- 爆点密度：{rhythm['beat_density']}")
        sections.append("\n".join(lines))

    # §3 爽点权重（爽点类型 %）
    weights = genre_dict.get("satisfaction_weights") or {}
    if weights:
        lines = ["## 爽点权重（按占比分配篇幅）"]
        for name, pct in weights.items():
            lines.append(f"- {name}：{pct}%")
        sections.append("\n".join(lines))

    # §4 守则
    rules = genre_dict.get("writing_rules") or []
    if rules:
        lines = ["## 写作守则（必做）"]
        lines += [f"- {r}" for r in rules]
        sections.append("\n".join(lines))

    # §5 不要做
    donts = genre_dict.get("donts") or []
    if donts:
        lines = ["## 禁忌（不要做）"]
        lines += [f"- {d}" for d in donts]
        sections.append("\n".join(lines))

    return "\n\n".join(sections)


def build_style_context(style_dict: dict, *, stage: str) -> str:
    """风格圣经 → 注入文本（复用 style_bible.inject_style_prompt）。

    - stage='ref'    → 含 ref_fingerprint（出 ref 图锁一致性）+ prompt_suffix + negative_suffix。
    - stage='render' → 不含 fingerprint（避免中性平光污染戏剧打光）+ prompt_suffix + negative_suffix。

    空 dict → 空串。
    """
    if not style_dict:
        return ""
    return inject_style_prompt("", style_dict, stage=stage)


def build_video_director_prompts(
    storyboard: dict,
    style_dict: dict,
    genre_dict: dict,
    *,
    fps: int,
) -> dict:
    """storyboard → 导演台视频提示词结构（LTX 2.3）。

    返回：
      {
        "global_prompt": "<style prompt_suffix + 全片基调>",
        "shots": [{"shot_id", "prompt"(镜头描述 + 风格), "length_frames", "duration"}, ...],
        "fps": fps,
        "total_frames": Σ length_frames,
      }

    时间公式：length_frames = round(duration * fps)；duration 缺省 3.0s。
    全局基调取自题材 identity.one_liner（题材驱动全片情绪）。
    """
    style_ctx = build_style_context(style_dict, stage="render")

    # 全局基调：风格 render 注入 + 题材一句话定位
    tone = ((genre_dict or {}).get("identity") or {}).get("one_liner", "")
    global_prompt = ", ".join(p for p in (style_ctx, tone) if p)

    shots_out: list[dict] = []
    total_frames = 0
    raw_shots = (storyboard or {}).get("shots") or []
    for i, shot in enumerate(raw_shots, start=1):
        shot_id = shot.get("id") or shot.get("shotId") or f"S{i:03d}"
        desc = shot.get("description") or shot.get("prompt") or ""
        duration = shot.get("duration")
        if duration is None:
            duration = _DEFAULT_DURATION
        length_frames = round(duration * fps)
        total_frames += length_frames

        prompt = ", ".join(p for p in (desc, style_ctx) if p)
        shots_out.append(
            {
                "shot_id": shot_id,
                "prompt": prompt,
                "length_frames": length_frames,
                "duration": duration,
            }
        )

    return {
        "global_prompt": global_prompt,
        "shots": shots_out,
        "fps": fps,
        "total_frames": total_frames,
    }


def guard_prompt(text: str, *, max_chars: int = 1400) -> str:
    """失败模式 guardrail（OnlyShot 失败模式 1/2）。

    - 禁词替换表：内容审核易拒词替换为安全近义词
      （sinister→moody / blush→rose tint / extreme close-up→medium shot）。
    - 超长截断：≤ max_chars（默认 1400，即梦 ≤1500 字安全余量）。
    """
    if not text:
        return text or ""
    out = text
    for bad, good in _BANNED_REPLACEMENTS:
        out = out.replace(bad, good)
    if len(out) > max_chars:
        out = out[:max_chars]
    return out


def _join(value) -> str:
    """列表 → 顿号连接；标量 → 原样字符串。"""
    if isinstance(value, (list, tuple)):
        return "、".join(str(v) for v in value)
    return str(value)
