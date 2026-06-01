"""media_agent FastAPI app + uvicorn 入口。镜像 screenwriter_agent.server。"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import MediaAgentConfig

# 仓库根：<repo>/media_agent/server.py → parent.parent
_REPO_ROOT = Path(__file__).resolve().parent.parent
_WEB_DIR = _REPO_ROOT / "web"


def create_app(cfg: MediaAgentConfig | None = None) -> FastAPI:
    cfg = cfg or MediaAgentConfig()
    app = FastAPI(title="media_agent", version="0.1.0")
    app.state.cfg = cfg

    # CORS：放行本地来源，使 file:// 页（Origin: null）与 127.0.0.1:* 直接 fetch，
    # 不再依赖浏览器 --disable-web-security。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["null"],
        allow_origin_regex=r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from .routes.health import router as health_router
    app.include_router(health_router)

    from .routes.imaging import router as imaging_router
    app.include_router(imaging_router)

    from .routes.transition import router as transition_router
    app.include_router(transition_router)

    from .routes.imggen import router as imggen_router
    app.include_router(imggen_router)

    from .routes.soundtrack import router as soundtrack_router
    app.include_router(soundtrack_router)

    from .routes.skills import router as skills_router
    app.include_router(skills_router)

    from .routes.assets import router as assets_router
    app.include_router(assets_router)

    from .routes.projects import router as projects_router
    app.include_router(projects_router)

    from .routes.config import router as config_router
    app.include_router(config_router)

    from .routes.projectx import router as projectx_router
    app.include_router(projectx_router)

    from .routes.files import router as files_router
    app.include_router(files_router)

    from .routes.tts import router as tts_router
    app.include_router(tts_router)

    from .routes.video import router as video_router
    app.include_router(video_router)

    # 静态同源托管 web/：经 http://127.0.0.1:18450/ui/ 访问（与 API 同源）。
    if _WEB_DIR.is_dir():
        app.mount("/ui", StaticFiles(directory=str(_WEB_DIR), html=True), name="ui")

    return app


def run(cfg: MediaAgentConfig | None = None) -> None:
    """启动 uvicorn。端口被占用时往后试 9 个。"""
    import uvicorn
    cfg = cfg or MediaAgentConfig()
    logging.basicConfig(level=cfg.log_level.upper())
    for offset in range(10):
        port = cfg.port + offset
        try:
            cfg.port = port
            uvicorn.run(create_app(cfg), host=cfg.host, port=port,
                        log_level=cfg.log_level)
            return
        except OSError as e:
            if "address already in use" not in str(e).lower():
                raise
    raise RuntimeError(f"端口 {cfg.port}+1..+9 都被占用")


if __name__ == "__main__":
    run()
