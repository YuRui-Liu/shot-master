"""FastAPI 入口：路由聚合 + 静态文件挂载 + 启动脚本入口"""
from __future__ import annotations

import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import load_config


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # 清空预览缓存（每次启动都重置）
    cache_dir = Path("app/.cache/preview")
    if cache_dir.exists():
        import shutil
        shutil.rmtree(cache_dir, ignore_errors=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    yield


def create_app() -> FastAPI:
    cfg = load_config()
    app = FastAPI(title="Shot-Prompt-Backwards", lifespan=_lifespan)
    app.state.config = cfg

    # 触发 provider 注册（必须在路由注册之前）
    import app.providers as _providers  # noqa: F401

    @app.get("/api/health")
    async def health():
        return {
            "status": "ok",
            "provider": cfg.current_provider,
            "model": cfg.current_model,
        }

    # 业务路由
    from app.api import inference as inference_api
    app.include_router(inference_api.router)

    # 静态资源
    web_dir = Path("web")
    if web_dir.exists():
        if (web_dir / "index.html").exists():
            @app.get("/")
            async def root():
                return FileResponse(web_dir / "index.html")
        app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

    # 预览缓存（拆图 tile 输出）以静态文件方式暴露
    cache_dir = Path("app/.cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/cache", StaticFiles(directory=str(cache_dir)), name="cache")

    return app


def run():
    """`shot-prompt-backwards` 命令入口（pyproject [project.scripts]）"""
    cfg = load_config()
    url = f"http://{cfg.host}:{cfg.port}"
    try:
        webbrowser.open(url)
    except Exception:
        pass
    uvicorn.run("app.main:create_app", factory=True,
                host=cfg.host, port=cfg.port, reload=False)


if __name__ == "__main__":
    run()
