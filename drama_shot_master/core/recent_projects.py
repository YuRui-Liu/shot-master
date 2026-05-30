"""最近项目列表：读写 recent_projects.json，最多 MAX 条，按最后打开时间降序。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class RecentProjectsManager:
    MAX = 8

    def __init__(self, path: Path):
        self._path = Path(path)

    @classmethod
    def alongside_settings(cls, settings_path: Path) -> "RecentProjectsManager":
        """与 settings.json 同目录。"""
        return cls(Path(settings_path).parent / "recent_projects.json")

    def load(self) -> list[dict]:
        """返回有效项目列表（path 必须存在），保持写入时的先后顺序（最近在前）。"""
        raw = self._read_raw()
        valid = [p for p in raw if Path(p.get("path", "")).exists()]
        if len(valid) != len(raw):
            self._write_raw(valid)
        return valid

    def push(self, path: str, name: str | None = None) -> None:
        """添加或更新一条记录，移至列表首位，裁剪至 MAX。"""
        path = str(Path(path))
        raw = self._read_raw()
        raw = [p for p in raw if p.get("path") != path]
        entry = {
            "name": name if name is not None else Path(path).name,
            "path": path,
            "last_opened": datetime.now(timezone.utc).isoformat(),
            "shot_count": 0,
        }
        raw.insert(0, entry)
        self._write_raw(raw[: self.MAX])

    def remove(self, path: str) -> None:
        """从列表中删除指定路径。"""
        path = str(Path(path))
        raw = [p for p in self._read_raw() if p.get("path") != path]
        self._write_raw(raw)

    def _read_raw(self) -> list[dict]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []

    def _write_raw(self, projects: list[dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(projects, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
