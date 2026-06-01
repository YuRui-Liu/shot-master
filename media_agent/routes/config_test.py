"""测试连接端点：服务端实测 LLM / RunningHub 连通性。

为什么放在服务端：浏览器直连第三方 API 会被 CORS 拦截，且 api_key 暴露在前端。
统一由 media_agent 后端用 openai 兼容客户端 / httpx 实测，回 {ok, message}。

两个工厂函数（_make_openai_client / _http_get）默认走真实依赖，测试可 monkeypatch
以零网络验证 ok / fail 两条路径。任何异常都被捕获成 {ok:false, message:...}，不抛 500。
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/config")

# openai 实测超时（秒）。ping 一条 max_tokens=1 的请求应在此内返回。
_LLM_TIMEOUT = 15.0
# RunningHub httpx 连通超时（秒）。
_RH_TIMEOUT = 15.0


# ---------- 可注入工厂（测试 monkeypatch 这两个） ----------

def _make_openai_client(*, base_url: str, api_key: str, timeout: float):
    """构造 openai 兼容客户端。默认真实 OpenAI；测试时被替换。"""
    from openai import OpenAI

    return OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)


def _http_get(url: str, *, headers: dict, timeout: float):
    """发一个 GET（默认真实 httpx）；测试时被替换。返回带 .status_code 的对象。"""
    import httpx

    return httpx.get(url, headers=headers, timeout=timeout)


# ---------- 请求体 ----------

class LLMTestBody(BaseModel):
    base_url: str
    api_key: str
    model: str | None = None


class RunningHubTestBody(BaseModel):
    api_key: str
    base_url: str | None = None


# ---------- POST /config/test/llm ----------

@router.post("/test/llm")
def test_llm(body: LLMTestBody):
    """服务端 openai 兼容实测：有 model → chat.completions(ping, max_tokens=1)，
    否则 models.list()。doubao(ark)/deepseek/openai 都走此路。

    任何异常捕获成 {ok:false, message:简短原因}，绝不抛 500。
    """
    base_url = (body.base_url or "").strip()
    api_key = (body.api_key or "").strip()
    if not base_url:
        return {"ok": False, "message": "缺少 base_url"}
    if not api_key:
        return {"ok": False, "message": "缺少 api_key"}

    try:
        client = _make_openai_client(
            base_url=base_url, api_key=api_key, timeout=_LLM_TIMEOUT)
        model = (body.model or "").strip()
        if model:
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
            return {"ok": True, "message": f"连接成功（模型 {model} 可用）"}
        client.models.list()
        return {"ok": True, "message": "连接成功（鉴权通过）"}
    except Exception as e:  # noqa: BLE001 — 任何错都降级为 ok:false
        return {"ok": False, "message": _brief(e)}


# ---------- POST /config/test/runninghub ----------

@router.post("/test/runninghub")
def test_runninghub(body: RunningHubTestBody):
    """服务端用 httpx 测 RunningHub 连通 + 鉴权。

    GET base_url 带 Bearer：200/2xx/3xx → 可达且未被拒；401/403 → 鉴权失败；
    其余状态码 → 报状态码。网络错 → 不可达。全部捕获，不抛 500。
    """
    api_key = (body.api_key or "").strip()
    base_url = (body.base_url or "").strip() or "https://www.runninghub.cn"
    base_url = base_url.rstrip("/")
    if not api_key:
        return {"ok": False, "message": "缺少 api_key"}

    try:
        resp = _http_get(
            base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=_RH_TIMEOUT,
        )
        code = resp.status_code
        if code in (401, 403):
            return {"ok": False, "message": f"鉴权失败（HTTP {code}）"}
        if code < 400:
            return {"ok": True, "message": "连接成功（服务可达）"}
        return {"ok": False, "message": f"服务返回 HTTP {code}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"连接失败：{_brief(e)}"}


def _brief(e: Exception) -> str:
    """异常 → 简短单行原因（截断，避免把整段 traceback 塞进 message）。"""
    msg = str(e).strip() or e.__class__.__name__
    return msg.splitlines()[0][:300]
