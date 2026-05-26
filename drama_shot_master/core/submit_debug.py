"""视频提交诊断日志（临时排查用）。

记录每次视频生成提交的：profile / workflow_id / 模板 / 上传图实际尺寸 /
完整 nodeInfoList。写到项目根目录的 video_submit_debug.log；MainWindow 关闭时
调用 reset() 自动删除（崩溃未正常关闭则保留，便于事后溯源）。

Qt-free，任何写入失败都静默吞掉，绝不影响提交主流程。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

# 项目根（cwd）下，方便溯源
LOG_PATH = Path("video_submit_debug.log").resolve()


def reset() -> None:
    """删除日志文件（MainWindow 关闭时调）。"""
    try:
        LOG_PATH.unlink()
    except (FileNotFoundError, OSError):
        pass


def write(line: str) -> None:
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {line}\n")
    except OSError:
        pass


def write_block(title: str, obj: object) -> None:
    """写一段标题 + JSON 化对象（用于 nodeInfoList）。"""
    write(title)
    try:
        text = json.dumps(obj, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        text = str(obj)
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(text + "\n")
    except OSError:
        pass
