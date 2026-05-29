"""Spawn screenwriter_agent 子进程；监控健康；优雅退出。"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


class ScreenwriterLifecycle:
    """单例：主软件启动时 spawn agent；退出时 terminate。"""

    def __init__(self, base_port: int = 18430, log_dir: Path | None = None,
                 cfg=None):
        self.base_port = base_port
        self.port = base_port
        self._cfg = cfg                     # 主软件 Config 实例（取 LLM 凭据）
        self._proc: subprocess.Popen | None = None
        self._log_dir = log_dir or (Path.home() / ".drama_shot_master" / "logs")
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._port_file = self._log_dir / ".screenwriter_port"
        self._pid_file = self._log_dir / ".screenwriter.pid"

    def spawn(self) -> int:
        """Spawn agent 子进程；poll /health 直到起来；返回实际监听端口。
        已运行则 no-op。"""
        if self._proc is not None and self._proc.poll() is None:
            return self.port
        log_path = self._log_dir / "screenwriter_agent.log"
        log_f = open(log_path, "ab")
        env = os.environ.copy()
        # 把主软件 cfg 的 LLM 凭据/平台配置注入 agent 子进程环境
        # ——agent 的 routes/ideate.py 等 handler 从 env 读 API_KEY / BASE_URL
        if self._cfg is not None:
            api_key = getattr(self._cfg, "screenwriter_llm_api_key", "") or ""
            base_url = getattr(self._cfg, "screenwriter_llm_base_url", "") or ""
            if api_key:
                env["SCREENWRITER_LLM_API_KEY"] = api_key
            if base_url:
                env["SCREENWRITER_LLM_BASE_URL"] = base_url
            # 兼容旧字段：若空，回退到 llm_providers["deepseek"] 等条目
            if not api_key or not base_url:
                providers = getattr(self._cfg, "llm_providers", {}) or {}
                # 优先 deepseek（agent 默认 base_url 即 deepseek）
                for pname in ("deepseek", "doubao", "openai"):
                    p = providers.get(pname) or {}
                    if not env.get("SCREENWRITER_LLM_API_KEY") and p.get("api_key"):
                        env["SCREENWRITER_LLM_API_KEY"] = p["api_key"]
                    if not env.get("SCREENWRITER_LLM_BASE_URL") and p.get("base_url"):
                        env["SCREENWRITER_LLM_BASE_URL"] = p["base_url"]
                    if env.get("SCREENWRITER_LLM_API_KEY") and env.get("SCREENWRITER_LLM_BASE_URL"):
                        break
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "screenwriter_agent",
             "--port", str(self.base_port)],
            stdout=log_f, stderr=subprocess.STDOUT,
            env=env, close_fds=True)
        self._pid_file.write_text(str(self._proc.pid))
        # 端口探测：从 base_port 往后试 +0..+9（agent 端口冲突会自己偏移）
        self.port = self._probe_listening_port(
            self.base_port, retries=20, sleep_s=0.3)
        return self.port

    def _probe_listening_port(self, base: int, *, retries: int, sleep_s: float) -> int:
        """每 sleep_s 轮询 base..base+9 的 /health；首个 200 即认作命中。
        全部失败 → 仍返回 base（caller 看到连接失败时会报 retry banner）。"""
        try:
            import urllib.request
            import urllib.error
        except ImportError:
            time.sleep(sleep_s * retries)
            return base
        for _ in range(retries):
            for offset in range(10):
                port = base + offset
                try:
                    with urllib.request.urlopen(
                            f"http://127.0.0.1:{port}/health",
                            timeout=0.3) as resp:
                        if 200 <= resp.status < 300:
                            try:
                                self._port_file.write_text(str(port))
                            except OSError:
                                pass
                            return port
                except (urllib.error.URLError, OSError, TimeoutError):
                    continue
            time.sleep(sleep_s)
            # 子进程已挂 → 不再 poll，直接返回 base 让 caller 报错
            if self._proc is None or self._proc.poll() is not None:
                break
        return base

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def terminate(self, timeout: float = 5.0) -> None:
        if self._proc is None:
            return
        if self._proc.poll() is not None:
            self._proc = None
            return
        try:
            self._proc.terminate()
            self._proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait(timeout=2.0)
        self._proc = None
        try:
            self._pid_file.unlink()
        except OSError:
            pass

    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"
