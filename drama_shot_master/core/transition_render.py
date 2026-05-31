"""成片渲染：由 CompositionModel 构建 ffmpeg(xfade+acrossfade) 参数并执行。Qt-free。

转场效果库 XFADE_EFFECTS 为 UI/渲染共用事实源（含类别 + 中文显示名）。
"""
from __future__ import annotations

import subprocess
from typing import Callable

from drama_shot_master.core.composition_model import CompositionModel

XFADE_EFFECTS = [
    {"name": "fade", "label": "淡入淡出", "category": "universal"},
    {"name": "fadeblack", "label": "黑场过渡", "category": "universal"},
    {"name": "fadewhite", "label": "白场过渡", "category": "universal"},
    {"name": "dissolve", "label": "叠化", "category": "universal"},
    {"name": "distance", "label": "距离溶解", "category": "universal"},
    {"name": "smoothleft", "label": "推进 ←", "category": "directional"},
    {"name": "smoothright", "label": "推进 →", "category": "directional"},
    {"name": "smoothup", "label": "推进 ↑", "category": "directional"},
    {"name": "smoothdown", "label": "推进 ↓", "category": "directional"},
    {"name": "slideleft", "label": "滑动 ←", "category": "directional"},
    {"name": "slideright", "label": "滑动 →", "category": "directional"},
    {"name": "wipeleft", "label": "擦除 ←", "category": "directional"},
    {"name": "wiperight", "label": "擦除 →", "category": "directional"},
    {"name": "circleopen", "label": "圆形展开", "category": "creative"},
    {"name": "circleclose", "label": "圆形收拢", "category": "creative"},
    {"name": "radial", "label": "径向", "category": "creative"},
    {"name": "zoomin", "label": "推近", "category": "creative"},
    {"name": "pixelize", "label": "像素化", "category": "creative"},
    {"name": "squeezev", "label": "纵向挤压", "category": "creative"},
    {"name": "none", "label": "硬切", "category": "cut"},
]


def compute_offsets(durations: list[float], trans_durs: list[float]) -> list[float]:
    """xfade 各切口 offset：off_i = Σdur[0..i] - Σt[0..i]。len = len(durations)-1。"""
    offs = []
    cum_d = 0.0
    cum_t = 0.0
    for i in range(len(durations) - 1):
        cum_d += durations[i]
        cum_t += trans_durs[i]
        offs.append(round(cum_d - cum_t, 3))
    return offs


def _norm_chain(idx: int, w: int, h: int, fps: int, pix: str) -> tuple[str, str]:
    v = (f"[{idx}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
         f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps={fps},format={pix},setsar=1[v{idx}]")
    a = (f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo[a{idx}]")
    return v, a


def build_ffmpeg_args(comp: CompositionModel, out_path: str,
                      ffmpeg: str, probe: Callable[[str], float]) -> list[str]:
    """构建 ffmpeg 参数列表。probe(path)->秒 用于实测时长（注入便于单测）。"""
    kept = comp.kept_clips()
    inputs: list[str] = []
    for c in kept:
        inputs += ["-i", c.path]

    durs = []
    for c in kept:
        base = probe(c.path) or c.duration
        start = c.in_point or 0.0
        end = c.out_point if c.out_point is not None else base
        durs.append(max(0.01, end - start))

    w, h, fps, pix = comp.width, comp.height, comp.fps, comp.pix_fmt
    parts: list[str] = []
    vlabels, alabels = [], []
    for i, c in enumerate(kept):
        vexpr, aexpr = _norm_chain(i, w, h, fps, pix)
        if c.in_point is not None or c.out_point is not None:
            ss = c.in_point or 0.0
            to = c.out_point if c.out_point is not None else durs[i] + ss
            vexpr = vexpr.replace(f"[{i}:v]", f"[{i}:v]trim=start={ss}:end={to},setpts=PTS-STARTPTS,")
            aexpr = aexpr.replace(f"[{i}:a]", f"[{i}:a]atrim=start={ss}:end={to},asetpts=PTS-STARTPTS,")
        parts.append(vexpr)
        parts.append(aexpr)
        vlabels.append(f"[v{i}]")
        alabels.append(f"[a{i}]")

    n = len(kept)
    trans = [c.effective_transition() for c in kept[:-1]]
    tdurs = [c.effective_duration() for c in kept[:-1]]

    if n == 1:
        filter_complex = ";".join(parts)
        vmap, amap = "[v0]", "[a0]"
    elif all(t == "none" for t in trans):
        concat_in = "".join(vlabels[i] + alabels[i] for i in range(n))
        parts.append(f"{concat_in}concat=n={n}:v=1:a=1[vout][aout]")
        filter_complex = ";".join(parts)
        vmap, amap = "[vout]", "[aout]"
    else:
        offs = compute_offsets(durs, tdurs)
        vcur, acur = vlabels[0], alabels[0]
        for i in range(1, n):
            t = trans[i - 1] if trans[i - 1] != "none" else "fade"
            d = tdurs[i - 1]
            off = offs[i - 1]
            vout = f"[vx{i}]" if i < n - 1 else "[vout]"
            aout = f"[ax{i}]" if i < n - 1 else "[aout]"
            parts.append(f"{vcur}{vlabels[i]}xfade=transition={t}:duration={d}:offset={off}{vout}")
            parts.append(f"{acur}{alabels[i]}acrossfade=d={d}{aout}")
            vcur, acur = vout, aout
        filter_complex = ";".join(parts)
        vmap, amap = "[vout]", "[aout]"

    return [
        ffmpeg, "-y", *inputs,
        "-filter_complex", filter_complex,
        "-map", vmap, "-map", amap,
        "-c:v", "libx264", "-pix_fmt", pix, "-c:a", "aac",
        out_path,
    ]


def render(comp: CompositionModel, out_path: str) -> str:
    """执行渲染（真调 ffmpeg）。成功返回 out_path，失败抛 RuntimeError。"""
    from drama_shot_master.core.ffmpeg_locate import ffmpeg_path, probe_duration
    args = build_ffmpeg_args(comp, out_path, ffmpeg=ffmpeg_path(), probe=probe_duration)
    proc = subprocess.run(args, capture_output=True, check=False)
    if proc.returncode != 0:
        tail = (proc.stderr or b"").decode("utf-8", "ignore")[-800:]
        raise RuntimeError(f"ffmpeg 渲染失败：\n{tail}")
    return out_path
