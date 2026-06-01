"""TTS 配音端点：音色设计(design) / 声音克隆(clone) 单条合成。复用原项目 TTS 管线。

设计取舍（对齐 soundtrack/imggen 路由）：
- 合成走 RunningHub（需网络/key），故 client 用模块级可注入工厂 `_client_factory`
  （默认 build RunningHubClient(cfg)）+ `_load_cfg`（默认 load_config）。测试 monkeypatch
  `_client_factory` 注入假 client（upload/create/query/download 全本地），不触网。
- profile 由 VOICE_DESIGN / VOICE_CLONE + cfg.dub_workflow_ids / cfg.dub_node_profiles
  覆盖得到（with_overrides）；workflow_id 也可由请求体显式覆盖。
- design：build_design_node_info(text, style, language, prof) 组 node_info。
- clone：speaker_file 先 upload_all 拿 RunningHub fileName，再 build_clone_node_info；
  mode 3 同理上传 emo_audio_file。
- 音频以文件路径传递；输出 FLAC 落 out_dir，返回 {output: flac_path}。
- /preview 同 synthesize 但落系统临时目录，供试听。

空 text / 缺 workflow_id → 400。
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from drama_shot_master.core import tts_profiles as P
from drama_shot_master.providers import tts_builder as B
from drama_shot_master.providers import tts_submit

router = APIRouter(prefix="/tts")


def _load_cfg():
    from drama_shot_master.config import load_config
    return load_config()


def _build_tts_client(cfg):
    """从 cfg 构造 RunningHub 客户端（TTS 合成走它）。"""
    from drama_shot_master.providers.runninghub import RunningHubClient
    return RunningHubClient(
        getattr(cfg, "runninghub_api_key", ""),
        base_url=getattr(cfg, "runninghub_base_url",
                         "https://www.runninghub.cn"))


# 可注入：测试替换为假 client 工厂（不触网）
_client_factory = _build_tts_client


def _resolve_profile(cfg, mode: str) -> P.TTSProfile:
    """据 mode 取基准 profile，叠加 cfg.dub_workflow_ids / dub_node_profiles 覆盖。"""
    ids = getattr(cfg, "dub_workflow_ids", {}) or {}
    nodes = getattr(cfg, "dub_node_profiles", {}) or {}
    if mode == "design":
        return P.with_overrides(P.VOICE_DESIGN, ids.get("voice_design"),
                                nodes.get("voice_design"))
    return P.with_overrides(P.VOICE_CLONE, ids.get("voice_clone"),
                            nodes.get("voice_clone"))


class SynthesizeRequest(BaseModel):
    text: str
    mode: str = "design"                 # 'design' | 'clone'
    language: str = "中文"
    # design：音色设计风格描述
    style: str = ""
    # clone：说话人参考音频 + 情感模式
    speaker_file: Optional[str] = None
    emo_mode: int = 1                    # 1 默认 / 2 文本 / 3 音频 / 4 向量
    emo_alpha: float = 1.0
    emo_text: str = ""
    emo_audio_file: Optional[str] = None
    emo_vector: Optional[list] = None
    sampling: Optional[dict] = None
    speed: Optional[float] = None        # 透传给 sampling（如工作流支持）
    # 显式覆盖工作流 ID（缺省取 profile/cfg）
    workflow_id: Optional[str] = None
    out_dir: str = ""
    base_name: str = ""


def _do_synthesize(req: SynthesizeRequest, out_dir: Path) -> str:
    if not req.text.strip():
        raise ValueError("text 不能为空")
    mode = (req.mode or "design").strip().lower()
    if mode not in ("design", "clone"):
        raise ValueError(f"未知 mode: {req.mode}")

    cfg = _load_cfg()
    prof = _resolve_profile(cfg, mode)
    workflow_id = (req.workflow_id or prof.workflow_id or "").strip()
    if not workflow_id:
        raise ValueError("缺少 workflow_id")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = (req.base_name or f"tts_{time.strftime('%Y%m%d_%H%M%S')}").strip()
    out_path = out_dir / f"{base}.flac"

    sampling = dict(req.sampling or {})
    if req.speed is not None:
        sampling.setdefault("speed", req.speed)

    client = _client_factory(cfg)

    if mode == "design":
        node_info = B.build_design_node_info(
            req.text, req.style, req.language, prof)
        result = tts_submit.submit_and_wait(
            client, workflow_id=workflow_id, node_info_list=node_info,
            out_path=out_path)
        return str(result)

    # clone：先上传参考音频拿 RunningHub fileName
    if not req.speaker_file:
        raise ValueError("clone 模式需要 speaker_file")
    spk = Path(req.speaker_file)
    emo_audio = (Path(req.emo_audio_file)
                 if (req.emo_mode == 3 and req.emo_audio_file) else None)
    uploads = [spk] + ([emo_audio] if emo_audio else [])
    mp = tts_submit.upload_all(client, uploads)
    node_info = B.build_clone_node_info(
        text=req.text, mode=int(req.emo_mode), emo_alpha=req.emo_alpha,
        speaker_file=mp[spk],
        emo_text=req.emo_text,
        emo_vector=req.emo_vector,
        emo_audio_file=mp.get(emo_audio) if emo_audio else None,
        sampling=sampling or None, prof=prof)
    result = tts_submit.submit_and_wait(
        client, workflow_id=workflow_id, node_info_list=node_info,
        out_path=out_path)
    return str(result)


@router.post("/synthesize")
def synthesize(req: SynthesizeRequest):
    if not req.out_dir.strip():
        raise HTTPException(status_code=400, detail="out_dir 不能为空")
    try:
        return {"output": _do_synthesize(req, Path(req.out_dir))}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/preview")
def preview(req: SynthesizeRequest):
    """同 synthesize，但落系统临时目录，供试听。"""
    tmp = Path(tempfile.mkdtemp(prefix="tts_preview_"))
    try:
        return {"output": _do_synthesize(req, tmp)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
