"""框选单片段生成：复用 BGM/SFX 现有管线 + audio_cache，产出一个叠加片段音频。

子项目 #3d-D3。被异步 worker（drama_shot_master.ui.widgets.daw.overlay_gen_worker）
调用：worker 只发信号，真正的「create_task→poll→download→缓存」全在这里。

- BGM：music_generator.generate_bgm(tags=用户prompt, bpm=默认, duration) 取首结果。
- SFX：sfx.generator.generate_sfx(prompt, clamp(duration,1,15), seed, out_path)。
- 缓存命中直接返回，未命中生成后入 audio_cache（work_dir/cache/{bgm,sfx}/）。
- client 缺省自建 RunningHubClient（读 cfg 鸭子属性）；测试一律注入假 client。
- 异常上抛（由 worker 捕获置 status=failed），本层不吞。
"""
from __future__ import annotations

from pathlib import Path

from sound_track_agent import audio_cache
from sound_track_agent.music_generator import generate_bgm
from sound_track_agent.sfx.generator import generate_sfx

# 默认参数（spec：无 emotion 反推，用户 prompt 直接当 tags）
_DEFAULT_BPM = 90
_DEFAULT_SEED = 1
# SFX 管线时长约束
_SFX_MIN_DUR = 1.0
_SFX_MAX_DUR = 15.0


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _build_client(cfg):
    """缺省自建 RunningHubClient（与 sfx.facade._build_client 同口径）。"""
    from drama_shot_master.providers.runninghub import RunningHubClient
    return RunningHubClient(
        getattr(cfg, "runninghub_api_key", ""),
        base_url=getattr(cfg, "runninghub_base_url",
                         "https://www.runninghub.cn"),
    )


def generate_overlay_clip(kind: str, prompt: str, duration: float, *,
                          work_dir, cfg, client=None) -> Path:
    """生成一个 overlay 片段音频，返回缓存内的音频 Path。

    kind: "bgm" | "sfx"；其它值抛 ValueError。异常上抛。
    """
    if kind not in ("bgm", "sfx"):
        raise ValueError(f"未知 overlay kind: {kind}")

    work_dir = Path(work_dir)
    if client is None:
        client = _build_client(cfg)

    if kind == "bgm":
        return _gen_bgm(client, cfg, prompt, float(duration), work_dir)
    return _gen_sfx(client, cfg, prompt, float(duration), work_dir)


def _gen_bgm(client, cfg, prompt: str, duration: float, work_dir: Path) -> Path:
    workflow_id = str(getattr(cfg, "soundtrack_workflow_id", ""))
    bpm = int(getattr(cfg, "overlay_bgm_bpm", _DEFAULT_BPM))
    cache_dir = work_dir / "cache" / "bgm"
    key = audio_cache.cache_key(workflow_id, prompt, bpm, duration, _DEFAULT_SEED)

    hit = audio_cache.lookup(cache_dir, key)
    if hit is not None:
        return hit

    # generate_bgm 下载到 stage_dir/bgm_seed{seed}.mp3，取首候选后移入缓存
    stage_dir = work_dir / "_overlay_stage" / "bgm"
    stage_dir.mkdir(parents=True, exist_ok=True)
    cands = generate_bgm(
        client, workflow_id,
        tags=prompt, bpm=bpm, duration=duration,
        out_dir=stage_dir, seeds=[_DEFAULT_SEED])
    src = Path(cands[0].path)
    return audio_cache.store(cache_dir, key, src)


def _gen_sfx(client, cfg, prompt: str, duration: float, work_dir: Path) -> Path:
    workflow_id = str(getattr(cfg, "sfx_workflow_id", ""))
    dur = _clamp(duration, _SFX_MIN_DUR, _SFX_MAX_DUR)
    cache_dir = work_dir / "cache" / "sfx"
    key = audio_cache.sfx_cache_key(workflow_id, prompt, dur, _DEFAULT_SEED)

    hit = audio_cache.lookup(cache_dir, key)
    if hit is not None:
        return hit

    stage_dir = work_dir / "_overlay_stage" / "sfx"
    stage_dir.mkdir(parents=True, exist_ok=True)
    out_path = stage_dir / f"sfx_{key}.mp3"
    src = generate_sfx(
        client, workflow_id,
        prompt=prompt, duration=dur, seed=_DEFAULT_SEED, out_path=out_path)
    return audio_cache.store(cache_dir, key, src)
