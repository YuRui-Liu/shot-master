"""Spawn screenwriter_agent 子进程；监控健康；优雅退出。"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


# 每个 LLM 平台的"通用入门"模型名（用户没在 [编剧] 阶段配 model 时兜底）。
# 这些名字保证在对应平台真实存在，不会被 400 model not found 而无声吞掉。
_PROVIDER_DEFAULT_MODELS = {
    "deepseek": "deepseek-v4-flash",   # DeepSeek 当前主推模型
    "doubao":   "doubao-1-5-thinking-pro-250415",
    "openai":   "gpt-4o-mini",
}


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
        """Spawn agent 子进程；先杀僵尸进程，poll /health 直到起来；
        返回实际监听端口。已运行则 no-op。"""
        if self._proc is not None and self._proc.poll() is None:
            return self.port
        # 先杀掉任何残留的旧 agent 进程（上次 main.py 没正常退出留下的僵尸）
        # ——否则旧进程占着 18430，新 agent 偏移到 18431，但 lifecycle 的 /health
        # 探测会先撞上旧的并误报"新 agent 已起"，主软件随后所有请求都打到旧 agent
        # 上跑老代码。
        self._kill_stale_process()
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
            # 全局兜底：若 legacy 无，从第一个有 key 的 provider 取（并记 fallback_provider，
            # 给"未配阶段分配"的 stage 推默认模型用）
            fallback_provider = ""
            if "SCREENWRITER_LLM_API_KEY" not in env or "SCREENWRITER_LLM_BASE_URL" not in env:
                for pname in ("deepseek", "doubao", "openai"):
                    p = providers.get(pname) or {}
                    if p.get("api_key") and "SCREENWRITER_LLM_API_KEY" not in env:
                        env["SCREENWRITER_LLM_API_KEY"] = p["api_key"]
                        fallback_provider = fallback_provider or pname
                    if p.get("base_url") and "SCREENWRITER_LLM_BASE_URL" not in env:
                        env["SCREENWRITER_LLM_BASE_URL"] = p["base_url"]
                        fallback_provider = fallback_provider or pname
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
                    # 用户没填 model → 用对应平台的 sane default（保证模型真存在）
                    if not model:
                        model = _PROVIDER_DEFAULT_MODELS.get(pname, "")
                # 用户连 stage assignment 都没填 → 全局 fallback provider 的默认 model
                # （否则 agent 会落到内置 default_models = doubao 名，对 deepseek 必空）
                if not model and fallback_provider:
                    model = _PROVIDER_DEFAULT_MODELS.get(fallback_provider, "")
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

    def _kill_stale_process(self) -> None:
        """杀掉 PID 文件里记录的进程（若仍存活）+ 关掉占着 base_port 的任何
        本机 listener（兜底）。Windows 用 taskkill /F /PID，Unix 用 SIGKILL。"""
        # Step 1: PID 文件路径
        if self._pid_file.is_file():
            try:
                pid = int(self._pid_file.read_text().strip())
            except (ValueError, OSError):
                pid = None
            if pid is not None:
                self._kill_pid(pid)
        # Step 2: 端口兜底——仍有进程监听 base_port → 强杀（覆盖 PID 文件丢失场景）
        self._kill_listener_on_port(self.base_port)
        # 给一点时间 OS 真正释放端口
        time.sleep(0.5)

    def _kill_pid(self, pid: int) -> None:
        """跨平台 kill PID。失败安静吞掉（可能已死）。"""
        if sys.platform == "win32":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True, timeout=5)
            except (subprocess.SubprocessError, OSError):
                pass
        else:
            try:
                import signal
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass

    def _kill_listener_on_port(self, port: int) -> None:
        """找到监听 :port 的 Python 进程并杀掉（用 ss/netstat 取 PID）。"""
        if sys.platform == "win32":
            try:
                # netstat -ano 列出 PID
                r = subprocess.run(
                    ["netstat", "-ano", "-p", "TCP"],
                    capture_output=True, text=True, timeout=5)
                for line in r.stdout.splitlines():
                    parts = line.split()
                    # 行格式: TCP 127.0.0.1:18430 0.0.0.0:0 LISTENING <PID>
                    if len(parts) >= 5 and parts[-1].isdigit() \
                            and f":{port}" in parts[1] \
                            and "LISTENING" in line:
                        self._kill_pid(int(parts[-1]))
            except (subprocess.SubprocessError, OSError):
                pass
        else:
            try:
                # ss 优先，没有则 lsof
                r = subprocess.run(
                    ["ss", "-tlnp", "sport", "=", f":{port}"],
                    capture_output=True, text=True, timeout=5)
                import re
                for m in re.finditer(r"pid=(\d+)", r.stdout):
                    self._kill_pid(int(m.group(1)))
            except (subprocess.SubprocessError, OSError, FileNotFoundError):
                pass

    def _probe_listening_port(self, base: int, *, retries: int, sleep_s: float) -> int:
        """每 sleep_s 轮询 base..base+9 的 /health；首个 200 且 PID 匹配认作命中。
        PID 不匹配（说明撞到僵尸进程）也强杀掉再继续探测。"""
        import json as _json
        try:
            import urllib.request
            import urllib.error
        except ImportError:
            time.sleep(sleep_s * retries)
            return base
        expected_pid = self._proc.pid if self._proc else 0
        for _ in range(retries):
            for offset in range(10):
                port = base + offset
                try:
                    with urllib.request.urlopen(
                            f"http://127.0.0.1:{port}/health",
                            timeout=0.3) as resp:
                        if 200 <= resp.status < 300:
                            try:
                                body = _json.loads(resp.read().decode("utf-8"))
                                agent_pid = int(body.get("pid", 0))
                            except Exception:
                                agent_pid = 0
                            # 校验是不是 OUR 进程
                            if agent_pid and agent_pid == expected_pid:
                                try:
                                    self._port_file.write_text(str(port))
                                except OSError:
                                    pass
                                return port
                            # 匹配不上 → 是僵尸进程占的，杀掉它，下一轮再探
                            if agent_pid and agent_pid != expected_pid:
                                self._kill_pid(agent_pid)
                            # /health 还没暴露 pid 字段（老版本 agent）→ 兜底接受
                            elif agent_pid == 0:
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
