"""GET /api/settings      — 当前配置 + 可用 provider 列表
PUT /api/settings      — 切换当前 provider/model（写 settings.json）
POST /api/settings/ping — 用 1×1 像素图测试 provider 连通性
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel
from PIL import Image

from app.providers import factory


router = APIRouter()


class UpdateSettingsRequest(BaseModel):
    current_provider: Optional[str] = None
    current_model: Optional[str] = None


class PingRequest(BaseModel):
    provider: str
    model: str


def _enumerate_providers() -> list[dict]:
    """枚举注册过的 provider + openai-compat 的所有 endpoint 子项。"""
    out = []
    for name in factory.list_providers():
        cls = factory.get_provider_class(name)
        if name == "openai_compat":
            for endpoint, preset in factory.openai_compat_presets().items():
                out.append({
                    "name": endpoint,
                    "kind": "openai_compat",
                    "models": preset["models"],
                    "base_url": preset["base_url"],
                })
        else:
            out.append({
                "name": name,
                "kind": name,
                "models": cls.available_models(),
                "base_url": "",
            })
    return out


@router.get("/api/settings")
async def get_settings(request: Request):
    cfg = request.app.state.config
    return {
        "current_provider": cfg.current_provider,
        "current_model": cfg.current_model,
        "default_provider": cfg.default_provider,
        "default_model": cfg.default_model,
        "default_output_dir": cfg.default_output_dir,
        "host": cfg.host,
        "port": cfg.port,
        "ui": cfg.ui,
        "providers": _enumerate_providers(),
        "configured_keys": sorted(cfg.api_keys.keys()),
    }


@router.put("/api/settings")
async def update_settings(req: UpdateSettingsRequest, request: Request):
    cfg = request.app.state.config
    updates = {}
    if req.current_provider is not None:
        updates["current_provider"] = req.current_provider
    if req.current_model is not None:
        updates["current_model"] = req.current_model
    cfg.update_settings(**updates)
    return {"current_provider": cfg.current_provider,
            "current_model": cfg.current_model}


@router.post("/api/settings/ping")
async def ping(req: PingRequest, request: Request):
    cfg = request.app.state.config
    # 1×1 透明 PNG
    buf = io.BytesIO()
    Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(buf, "PNG")
    tmp = Path("app/.cache/ping.png")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(buf.getvalue())
    try:
        provider = factory.build_provider(cfg, provider_name=req.provider, model=req.model)
        provider.generate([tmp], "回答一个字: ok", "")
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
