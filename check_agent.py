"""直接 POST 到 agent /ideate/chat，打印原始 HTTP 响应（绕过 SSE 解析）。

LLM 直连已 PASS（check_llm.py），但 agent 502。这里目标：看 agent
返的是真 HTTP 502 还是别的状态码、响应体长什么样（含 traceback HTML？）。

用法：
  # 需要已经 python -m drama_shot_master.main 跑着（保留 agent 子进程）
  python check_agent.py                                  # 用默认项目+测试 context
  python check_agent.py --project E:\\DramaAsserts\\scripts\\测试
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=None,
                    help="不填则读 cfg.screenwriter_agent_port")
    ap.add_argument("--project", default=None,
                    help="项目目录绝对路径；不填则用 cwd 下的 ./_check_agent_tmp/")
    args = ap.parse_args()

    if args.port is None:
        try:
            from drama_shot_master.config import load_config
            cfg = load_config()
            args.port = cfg.screenwriter_agent_port
        except Exception:
            args.port = 18430

    if args.project is None:
        proj = Path("_check_agent_tmp").resolve()
        proj.mkdir(exist_ok=True)
    else:
        proj = Path(args.project)
        if not proj.exists():
            print(f"[err] 项目目录不存在：{proj}")
            return 2

    base_url = f"http://{args.host}:{args.port}"
    print("=" * 60)
    print(f"  agent    : {base_url}")
    print(f"  project  : {proj}")
    print("=" * 60)

    # 0) 打印代理相关 env（HTTP_PROXY 设了会让 httpx 把 127.0.0.1 也路由过去 → 502）
    import os
    print("\n[env] 代理相关环境变量：")
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
               "http_proxy", "https_proxy", "all_proxy", "no_proxy"):
        v = os.environ.get(k)
        print(f"  {k}={v!r}")

    # 1) health 探活
    try:
        import httpx
    except ImportError:
        print("[err] 没装 httpx")
        return 2
    print(f"\n[info] httpx version: {httpx.__version__}")

    # 1a) 默认 httpx（trust_env=True）—— 与主软件相同
    print("\n--- /health 默认 httpx（trust_env=True，可能走代理） ---")
    try:
        r = httpx.get(f"{base_url}/health", timeout=3.0)
        print(f"[health.default] HTTP {r.status_code} body={r.text[:200]!r}")
    except Exception as e:
        print(f"[health.default] FAIL: {type(e).__name__}: {e}")

    # 1b) trust_env=False httpx —— 绕过环境代理设置
    print("\n--- /health trust_env=False httpx（强制直连 127.0.0.1） ---")
    try:
        with httpx.Client(trust_env=False, timeout=3.0) as c:
            r = c.get(f"{base_url}/health")
            print(f"[health.no_env] HTTP {r.status_code} body={r.text[:200]!r}")
    except Exception as e:
        print(f"[health.no_env] FAIL: {type(e).__name__}: {e}")

    # 1c) urllib 对照（lifecycle 用的就是 urllib，PASS 过）
    print("\n--- /health urllib（对照组） ---")
    try:
        import urllib.request
        with urllib.request.urlopen(f"{base_url}/health", timeout=3.0) as resp:
            body = resp.read().decode("utf-8", errors="replace")[:200]
            print(f"[health.urllib] HTTP {resp.status} body={body!r}")
    except Exception as e:
        print(f"[health.urllib] FAIL: {type(e).__name__}: {e}")
        return 1

    # 2) POST /ideate/chat（与主软件一样的 body）
    body = {
        "project_dir": str(proj),
        "context": {
            "core_idea": "守株待兔",
            "genre_tags": ["古风", "寓言"],
            "format": "短剧",
            "tone_tags": [],
            "visual_style": "水墨",
            "candidate_count": 3,
            "duration_sec": 60,
            "extra_constraints": "",
        },
        "messages": [{"role": "user", "content": "生成候选（按上面 context）"}],
        "auto_save_idea_json": True,
    }
    print("\n[ideate/chat] POST body:")
    print(json.dumps(body, ensure_ascii=False, indent=2))
    print()

    # 用 stream=True 拿原始字节，自己解 SSE，方便看到错误状态码 + 完整响应体
    # 同时同时跑两次：默认 httpx + trust_env=False，看 502 是不是代理引起
    print("\n--- /ideate/chat A: 默认 httpx（trust_env=True，主软件路径） ---")
    try:
        with httpx.Client(timeout=None) as c:
            with c.stream("POST", f"{base_url}/ideate/chat", json=body) as resp:
                print(f"[ideate/chat] HTTP {resp.status_code}")
                print(f"[ideate/chat] headers:")
                for k, v in resp.headers.items():
                    print(f"  {k}: {v}")
                print(f"[ideate/chat] body:")
                # 把字节都吃下来，不解 SSE
                body_bytes = b""
                for chunk in resp.iter_bytes():
                    body_bytes += chunk
                try:
                    print(body_bytes.decode("utf-8"))
                except UnicodeDecodeError:
                    print(repr(body_bytes[:2000]))
                print(f"\n[ideate/chat.A] total bytes: {len(body_bytes)}")
    except Exception as e:
        print(f"\n[ideate/chat.A] EXCEPTION: {type(e).__name__}: {e}")
        traceback.print_exc()

    # B: trust_env=False —— 绕过代理
    print("\n--- /ideate/chat B: trust_env=False（强制直连，绕代理） ---")
    try:
        with httpx.Client(timeout=None, trust_env=False) as c:
            with c.stream("POST", f"{base_url}/ideate/chat", json=body) as resp:
                print(f"[ideate/chat.B] HTTP {resp.status_code}")
                body_bytes = b""
                for chunk in resp.iter_bytes():
                    body_bytes += chunk
                try:
                    print(body_bytes.decode("utf-8")[:3000])
                except UnicodeDecodeError:
                    print(repr(body_bytes[:1500]))
                print(f"\n[ideate/chat.B] total bytes: {len(body_bytes)}")
    except Exception as e:
        print(f"\n[ideate/chat.B] EXCEPTION: {type(e).__name__}: {e}")
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("诊断结论：")
    print("  A 502 + B PASS  → 代理拦截 127.0.0.1，修法：客户端 trust_env=False")
    print("  A 与 B 同样 502 → 不是代理；看 body 和 agent log 找真实异常")
    print("  A 与 B 都 PASS  → bug 是主软件 GUI 触发路径特有的（不是 HTTP 层）")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
