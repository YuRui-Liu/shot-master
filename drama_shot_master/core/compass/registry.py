"""文件罗盘协议 · 全局注册表 registry（index.json）。

三层 manifest 的顶层：<projects_root>/index.json，索引所有项目。
schema_version / next_id（P-NNN 自增）/ projects[]（逐项目摘要）。

纯逻辑、无 Qt，全单测。字段形状照 research §2.2。
原则：
- **缺失自愈**：index.json 不存在/坏 JSON/非 dict → 以
  {schema_version:1, next_id:"P-001", projects:[]} 初始化，不崩。
- **禁硬编码 ID**：新建项目必走 allocate_id() 读注册表自增。
WelcomePage 的 ProjectCard 直接渲染 projects[]。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

# index.json 在 projects_root 下的固定文件名
INDEX_FILENAME = "index.json"

# next_id 形状：P-001、P-012 …（三位补零）
DEFAULT_NEXT_ID = "P-001"
_ID_RE = re.compile(r"^P-(\d+)$")


def _now_iso() -> str:
    """本地时区 ISO 时间戳。"""
    return datetime.now(timezone.utc).astimezone().isoformat()


def _format_id(n: int) -> str:
    """整数 → P-NNN（三位补零，超过仍按位数展开）。"""
    return f"P-{n:03d}"


def _parse_id(pid: object) -> Optional[int]:
    """P-NNN → 整数序号；形状坏 → None。"""
    if not isinstance(pid, str):
        return None
    m = _ID_RE.match(pid.strip())
    return int(m.group(1)) if m else None


def _resolve_path(path: Union[str, Path]) -> Path:
    """传目录则自动拼 index.json；传文件则原样。"""
    p = Path(path)
    if p.is_dir() or p.suffix == "":
        return p / INDEX_FILENAME
    return p


class ProjectRegistry:
    """全局注册表 index.json 的读写门面。

    构造即加载（缺失/坏文件自愈）。改动后须 save() 落盘。
    """

    def __init__(self, path: Union[str, Path]):
        self._path = _resolve_path(path)
        self.schema_version: int = 1
        self.next_id: str = DEFAULT_NEXT_ID
        self._projects: list[dict] = []
        self._load()

    # ---- 加载 / 自愈 -------------------------------------------------

    def _load(self) -> None:
        """读 index.json；缺失/坏 JSON/非 dict/坏 next_id → 自愈默认骨架。"""
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
            data = None
        if not isinstance(data, dict):
            data = {}

        self.schema_version = int(data.get("schema_version") or 1)

        # next_id 形状校验：坏（非 P-NNN）→ 退回 P-001
        raw_next = data.get("next_id")
        self.next_id = raw_next if _parse_id(raw_next) is not None else DEFAULT_NEXT_ID

        raw_projects = data.get("projects")
        self._projects = (
            [dict(p) for p in raw_projects if isinstance(p, dict)]
            if isinstance(raw_projects, list)
            else []
        )

    # ---- ID 分配（自增） ---------------------------------------------

    def allocate_id(self) -> str:
        """返回当前 next_id 并把 next_id 推进到下一个（P-001 → P-002）。

        坏 next_id 已在加载时自愈为 P-001；此处再兜底一次。
        """
        n = _parse_id(self.next_id)
        if n is None:
            n = 1
            self.next_id = _format_id(n)
        allocated = self.next_id
        self.next_id = _format_id(n + 1)
        return allocated

    # ---- 注册 / 列举 -------------------------------------------------

    def _find(self, project_id: str) -> Optional[dict]:
        for s in self._projects:
            if s.get("project_id") == project_id:
                return s
        return None

    def register(self, summary: dict) -> dict:
        """登记一个项目摘要；同 project_id 已存在则覆盖（不重复追加）。

        补齐 created_at / last_modified 时间戳。返回入库后的摘要。
        """
        summary = dict(summary or {})
        pid = summary.get("project_id")
        now = _now_iso()

        existing = self._find(pid) if pid else None
        if existing is not None:
            # 覆盖既有：保留原 created_at
            created = existing.get("created_at") or now
            existing.clear()
            existing.update(summary)
            existing["created_at"] = summary.get("created_at") or created
            existing["last_modified"] = now
            return existing

        summary.setdefault("created_at", now)
        summary["last_modified"] = now
        self._projects.append(summary)
        return summary

    def list_projects(self) -> list[dict]:
        """返回所有项目摘要的副本列表（外部改动不污染内部状态）。"""
        return [dict(s) for s in self._projects]

    def update_summary(self, project_id: str, **fields) -> None:
        """更新指定项目摘要字段（status/completed_episodes/cover/last_modified…）。

        未知 project_id → no-op 不抛、不新增。刷新 last_modified。
        """
        s = self._find(project_id)
        if s is None:
            return
        s.update(fields)
        s["last_modified"] = fields.get("last_modified") or _now_iso()

    # ---- 序列化 / 落盘 -----------------------------------------------

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "last_updated": _now_iso(),
            "next_id": self.next_id,
            "projects": [dict(s) for s in self._projects],
        }

    def save(self) -> Path:
        """落盘 index.json：utf-8、缩进、不转义中文。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return self._path
