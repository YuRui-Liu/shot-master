"""出图端点：单张/批量生成。复用 providers.image_gen（Doubao/OpenAI/RunningHub）。

provider 需 API key/网络，故工厂用模块级 `_provider_factory`（测试可 monkeypatch
注入假 provider 验证存盘管线，不打真实网络）。批量走 TaskRunner → SSE。
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from drama_shot_master.providers.image_gen import make_image_provider
from drama_shot_master.core.task_runner import TaskRunner, TaskItem
from media_agent.core.sse import sse_event

router = APIRouter(prefix="/imggen")

logger = logging.getLogger(__name__)

_DEFAULT_GEN_TIMEOUT = 120.0  # 秒

# 可注入：测试替换为假 provider 工厂
_provider_factory = make_image_provider


def _load_cfg():
    from drama_shot_master.config import load_config
    return load_config()


class GenRequest(BaseModel):
    prompt: str
    references: list[str] = []
    size: str = "1024x1024"
    n: int = 1
    out_dir: str
    base_name: str = "img"
    ext: str = "png"


def _do_generate(req: GenRequest) -> list[str]:
    if not req.prompt.strip():
        raise ValueError("prompt 不能为空")
    provider = _provider_factory(_load_cfg())
    images = provider.generate(
        req.prompt, [Path(p) for p in req.references], size=req.size, n=req.n)
    out_dir = Path(req.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[str] = []
    for i, data in enumerate(images):
        p = out_dir / f"{req.base_name}_{i:02d}.{req.ext}"
        p.write_bytes(data)
        outputs.append(str(p))
    return outputs


@router.post("/generate")
async def generate(req: GenRequest):
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_do_generate, req),
            timeout=_DEFAULT_GEN_TIMEOUT,
        )
        return {"outputs": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except asyncio.TimeoutError:
        logger.error(f"图像生成超时(>{_DEFAULT_GEN_TIMEOUT}s): prompt={req.prompt[:80]}")
        raise HTTPException(status_code=504, detail=f"图像生成超时(>{_DEFAULT_GEN_TIMEOUT}s)")
    except Exception as e:
        logger.error(f"图像生成失败(generate): {e}")
        raise HTTPException(status_code=500, detail=f"图像生成失败: {str(e)[:200]}")


class BatchGenRequest(BaseModel):
    items: list[GenRequest]


@router.post("/batch_generate")
async def batch_generate(req: BatchGenRequest):
    """批量出图 → SSE（对齐 TaskEvent）。单项失败不中断后续。"""
    items = [TaskItem(idx=i, payload={"req": r}, base_name=r.base_name)
             for i, r in enumerate(req.items)]

    async def worker(item: TaskItem) -> dict:
        r: GenRequest = item.payload["req"]
        outputs = await asyncio.wait_for(
            asyncio.to_thread(_do_generate, r),
            timeout=_DEFAULT_GEN_TIMEOUT,
        )
        return {"outputs": outputs}

    runner = TaskRunner(items, worker)

    async def gen():
        async for ev in runner.stream():
            yield sse_event(ev.type, ev.payload)

    return StreamingResponse(gen(), media_type="text/event-stream")
