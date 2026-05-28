"""Spawn screenwriter_agent 子进程；监控健康；优雅退出。"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


class ScreenwriterLifecycle:
    """单例：主软件启动时 spawn agent；退出时 terminate。"""

    def __init__(self, base_port: int = 18430, log_dir: Path | None = None):
        self.base_port = base_port
        self.port = base_port
        self._proc: subprocess.Popen | None = None
        self._log_dir = log_dir or (Path.home() / ".drama_shot_master" / "logs")
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._port_file = self._log_dir / ".screenwriter_port"
        self._pid_file = self._log_dir / ".screenwriter.pid"

    def spawn(self) -> int:
        """Spawn agent 子进程；返回实际端口。已运行则 no-op。"""
        if self._proc is not None and self._proc.poll() is None:
            return self.port
        log_path = self._log_dir / "screenwriter_agent.log"
        log_f = open(log_path, "ab")
        env = os.environ.copy()
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "screenwriter_agent",
             "--port", str(self.base_port)],
            stdout=log_f, stderr=subprocess.STDOUT,
            env=env, close_fds=True)
        self.port = self.base_port  # 端口冲突时 agent 自己 +1..+9，端口写到 .port 文件
        self._pid_file.write_text(str(self._proc.pid))
        # 给 1 秒等 agent 起来
        time.sleep(1.0)
        return self.port

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
