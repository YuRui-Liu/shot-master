"""成片渲染：由 CompositionModel 构建 ffmpeg(xfade+acrossfade) 参数并执行。Qt-free。

转场效果库 XFADE_EFFECTS 为 UI/渲染共用事实源（含类别 + 中文显示名）。
分类：universal(通用) / directional(方向) / fx(特效) / cut(切)。约 20 种。
TRANSITIONS 为 spec 用名的别名，指向同一事实源。

子项目2 新增特效类（均为合法 ffmpeg xfade transition 名）：
    circleopen / circleclose / radial / pixelize / zoomin / diagtl / hlslice
⚠ 个别 xfade 名在部分 ffmpeg 构建上可能不被支持——落地后逐个验渲染，
  对本机 ffmpeg 不支持的名字应从本表剔除（build_ffmpeg_args 直传该名，
  不支持时 ffmpeg 会在渲染期报错）。
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from drama_shot_master.core.composition_model import CompositionModel

XFADE_EFFECTS = [
    {"name": "fade", "label": "淡入淡出", "category": "universal"},
    {"name": "fadeblack", "label": "黑场过渡", "category": "universal"},
    {"name": "fadewhite", "label": "白场过渡", "category": "universal"},
    {"name": "dissolve", "label": "叠化", "category": "universal"},
    {"name": "smoothleft", "label": "推进 ←", "category": "directional"},
    {"name": "smoothright", "label": "推进 →", "category": "directional"},
    {"name": "smoothup", "label": "推进 ↑", "category": "directional"},
    {"name": "smoothdown", "label": "推进 ↓", "category": "directional"},
    {"name": "slideleft", "label": "滑动 ←", "category": "directional"},
    {"name": "slideright", "label": "滑动 →", "category": "directional"},
    {"name": "wipeleft", "label": "擦除 ←", "category": "directional"},
    {"name": "wiperight", "label": "擦除 →", "category": "directional"},
    # —— fx 特效（子项目2 新增，落地后逐个验渲染，不支持的剔除）——
    {"name": "circleopen", "label": "圆形展开", "category": "fx"},
    {"name": "circleclose", "label": "圆形收拢", "category": "fx"},
    {"name": "radial", "label": "径向", "category": "fx"},
    {"name": "pixelize", "label": "像素化", "category": "fx"},
    {"name": "zoomin", "label": "推近", "category": "fx"},
    {"name": "diagtl", "label": "对角 ↖", "category": "fx"},
    {"name": "hlslice", "label": "百叶窗", "category": "fx"},
    {"name": "none", "label": "硬切", "category": "cut"},
]

# spec 以 TRANSITIONS 指代效果库；保留 XFADE_EFFECTS 为既有事实源名，别名指向同一对象。
TRANSITIONS = XFADE_EFFECTS


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
    # settb/asettb 统一时间基：xfade/acrossfade 要求两路输入时间基一致；
    # 否则 concat 输出(1/1000000)与归一化片段(1/30)混用会报
    # "input link timebases do not match" 而整体失败。
    v = (f"[{idx}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
         f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps={fps},format={pix},setsar=1,"
         f"settb=1/{fps}[v{idx}]")
    a = (f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,"
         f"asettb=1/48000[a{idx}]")
    return v, a


def build_ffmpeg_args(comp: CompositionModel, out_path: str,
                      ffmpeg: str, probe: Callable[[str], float],
                      has_audio: Callable[[str], bool] | None = None) -> list[str]:
    """构建 ffmpeg 参数列表。probe(path)->秒 用于实测时长（注入便于单测）。
    has_audio(path)->bool 判断片段是否有音轨（None 时默认全有）。
    """
    # Bug 4: guard against empty kept list
    kept = comp.kept_clips()
    if len(kept) == 0:
        raise ValueError("没有保留的片段")

    # Default: treat all clips as having audio
    if has_audio is None:
        has_audio = lambda p: True

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

        # Bug 1: audio-stream guard — synthesize silence for clips without audio
        if has_audio(c.path):
            parts.append(aexpr)
        else:
            dur_i = durs[i]
            silence = (f"anullsrc=channel_layout=stereo:sample_rate=48000,"
                       f"atrim=duration={dur_i},asetpts=PTS-STARTPTS,"
                       f"asettb=1/48000[a{i}]")
            parts.append(silence)

        vlabels.append(f"[v{i}]")
        alabels.append(f"[a{i}]")

    n = len(kept)
    trans = [c.effective_transition() for c in kept[:-1]]
    tdurs = [c.effective_duration() for c in kept[:-1]]

    # FIX m3: degrade transition to hard cut when transition duration >= min clip length
    eff_trans = []
    eff_tdurs = []
    for k in range(len(trans)):
        t_name = trans[k]
        t_dur = tdurs[k]
        if t_name != "none" and t_dur >= min(durs[k], durs[k + 1]):
            eff_trans.append("none")
            eff_tdurs.append(0.0)
        else:
            eff_trans.append(t_name)
            eff_tdurs.append(t_dur)

    if n == 1:
        filter_complex = ";".join(parts)
        vmap, amap = "[v0]", "[a0]"
    elif all(t == "none" for t in eff_trans):
        # Fast path: single concat for all-none transitions
        concat_in = "".join(vlabels[i] + alabels[i] for i in range(n))
        parts.append(f"{concat_in}concat=n={n}:v=1:a=1[vout][aout]")
        filter_complex = ";".join(parts)
        vmap, amap = "[vout]", "[aout]"
    else:
        # Bug 2: fold-left accumulator — handles mixed none+xfade independently per boundary
        vcur, acur = vlabels[0], alabels[0]
        acc = durs[0]  # running video duration from clip 0
        for i in range(1, n):
            t = eff_trans[i - 1]
            d = eff_tdurs[i - 1]
            is_last = (i == n - 1)
            vout = "[vout]" if is_last else f"[vx{i}]"
            aout = "[aout]" if is_last else f"[ax{i}]"

            if t == "none":
                # Hard cut via concat (no overlap)。concat 会把时间基重置为 1/1000000，
                # 若其输出随后喂给 xfade/acrossfade 会与归一化片段(1/30, 1/48000)不匹配，
                # 故在 concat 后补 settb/asettb 还原统一时间基。
                parts.append(f"{vcur}{vlabels[i]}concat=n=2:v=1:a=0,settb=1/{fps}{vout}")
                parts.append(f"{acur}{alabels[i]}concat=n=2:v=0:a=1,asettb=1/48000{aout}")
                acc += durs[i]
            else:
                # xfade / acrossfade with fold-left offset
                off = max(0.0, round(acc - d, 3))
                parts.append(f"{vcur}{vlabels[i]}xfade=transition={t}:duration={d}:offset={off}{vout}")
                parts.append(f"{acur}{alabels[i]}acrossfade=d={d}{aout}")
                acc += durs[i] - d

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
    from drama_shot_master.core.ffmpeg_locate import ffmpeg_path, probe_duration, has_audio_stream
    # 确保输出目录存在（外部导入路径 / 新项目首次渲染时目录可能未创建）
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    args = build_ffmpeg_args(comp, out_path, ffmpeg=ffmpeg_path(), probe=probe_duration,
                             has_audio=has_audio_stream)
    proc = subprocess.run(args, capture_output=True, check=False)
    if proc.returncode != 0:
        tail = (proc.stderr or b"").decode("utf-8", "ignore")[-800:]
        raise RuntimeError(f"ffmpeg 渲染失败：\n{tail}")
    return out_path
