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
        # 把主软件 cfg 的 LLM 凭据/平台/per-stage 配置注入 agent 子进程环境。
        # agent 的 4 个 route（ideate/script/storyboard/prompts）按 stage 读
        # SCREENWRITER_{STAGE}_API_KEY / _BASE_URL / _MODEL；若 stage 级 env
        # 为空则回退到 SCREENWRITER_LLM_*（向后兼容）
        if self._cfg is not None:
            providers = getattr(self._cfg, "llm_providers", {}) or {}
            stage_assigns = getattr(self._cfg, "screenwriter_stage_assignments", {}) or {}
            # legacy 全局凭据
            legacy_key = getattr(self._cfg, "screenwriter_llm_api_key", "") or ""
            legacy_url = getattr(self._cfg, "screenwriter_llm_base_url", "") or ""
            if legacy_key:
                env["SCREENWRITER_LLM_API_KEY"] = legacy_key
            if legacy_url:
                env["SCREENWRITER_LLM_BASE_URL"] = legacy_url
            # 全局兜底：若 legacy 无，从第一个有 key 的 provider 取
            if "SCREENWRITER_LLM_API_KEY" not in env or "SCREENWRITER_LLM_BASE_URL" not in env:
                for pname in ("deepseek", "doubao", "openai"):
                    p = providers.get(pname) or {}
                    if p.get("api_key") and "SCREENWRITER_LLM_API_KEY" not in env:
                        env["SCREENWRITER_LLM_API_KEY"] = p["api_key"]
                    if p.get("base_url") and "SCREENWRITER_LLM_BASE_URL" not in env:
                        env["SCREENWRITER_LLM_BASE_URL"] = p["base_url"]
                    if "SCREENWRITER_LLM_API_KEY" in env and "SCREENWRITER_LLM_BASE_URL" in env:
                        break
            # 每个 stage 的 per-stage 注入（provider + model + api_key + base_url）
            for stage in ("ideate", "script", "storyboard", "prompts"):
                assign = stage_assigns.get(stage) or {}
                pname = assign.get("provider") or ""
                model = assign.get("model") or ""
                upper = stage.upper()
                if pname:
                    env[f"SCREENWRITER_{upper}_PROVIDER"] = pname
                    p = providers.get(pname) or {}
                    if p.get("api_key"):
                        env[f"SCREENWRITER_{upper}_API_KEY"] = p["api_key"]
                    if p.get("base_url"):
                        env[f"SCREENWRITER_{upper}_BASE_URL"] = p["base_url"]
                if model:
                    env[f"SCREENWRITER_{upper}_MODEL"] = model
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
