"""GET /health。返回 status + version + default_models + pid。"""
import os

from fastapi import APIRouter, Request

from screenwriter_agent import __version__

router = APIRouter()


@router.get("/health")
def health(request: Request):
    cfg = request.app.state.cfg
    return {
        "status": "ok",
        "version": __version__,
        "default_models": cfg.default_models,
        "pid": os.getpid(),    # 给主软件 lifecycle 验证是不是它新 spawn 的进程
    }
