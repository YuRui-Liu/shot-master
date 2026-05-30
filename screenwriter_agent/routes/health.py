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
        "pid": os.getpid(),    # 仅诊断用（Windows venv 启动器壳下 PID 不可靠）
        # nonce：主软件 spawn 时经 env 注入，用于识别"是不是本次 spawn 的 agent"，
        # 不受 venv 启动器/重定向导致的 PID 不匹配影响
        "nonce": os.environ.get("SCREENWRITER_AGENT_NONCE", ""),
    }
