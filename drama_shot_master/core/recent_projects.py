"""最近项目列表：读写 recent_projects.json，最多 MAX 条，按最后打开时间降序。

双轨并存（B3）：push() 在写 recent_projects.json 之外，同步登记到项目所在
projects_root 的全局注册表 index.json（compass.registry）。recent.json 原行为
完全保留；registry 操作 try/except 降级不崩，绝不影响 recent 主流程。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

# 目录名形如 {P-NNN}_{slug} 时，从前缀抽 project_id（与 compass.migrate 对齐）
_DIR_ID_RE = re.compile(r"^(P-\d+)(?:_.*)?$")


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

        # 双轨并存：同步登记进项目所在 projects_root 的全局注册表。
        # 任何异常都降级吞掉，绝不影响上面已完成的 recent 主流程。
        try:
            self._sync_registry(path, entry["name"])
        except Exception:  # noqa: BLE001 — registry 降级不崩
            pass

    def _sync_registry(self, project_path: str, name: str) -> None:
        """把项目同步登记进 <projects_root>/index.json（projects_root = 项目父目录）。

        - project_id 优先取目录名前缀 P-NNN；缺失则向 registry allocate_id 补建。
        - 已存在同 project_id → register 覆盖 / update_summary，不重复追加（防漂移）。
        - 与 recent_projects.json 双轨并存，互不替代。
        """
        from .compass.registry import ProjectRegistry

        proj_dir = Path(project_path)
        projects_root = proj_dir.parent

        reg = ProjectRegistry(projects_root)

        m = _DIR_ID_RE.match(proj_dir.name)
        project_id = m.group(1) if m else ""

        existing = None
        if project_id:
            existing = next(
                (
                    s
                    for s in reg.list_projects()
                    if s.get("project_id") == project_id
                ),
                None,
            )

        if existing is not None:
            # 已在册：仅刷新摘要，不重复追加。
            reg.update_summary(
                project_id, project_name=name, dir=proj_dir.name + "/"
            )
        else:
            # 缺 project_id（目录无前缀）→ allocate_id 补建一个稳定身份。
            if not project_id:
                project_id = reg.allocate_id()
            reg.register(
                {
                    "project_id": project_id,
                    "project_name": name,
                    "dir": proj_dir.name + "/",
                }
            )

        reg.save()

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
