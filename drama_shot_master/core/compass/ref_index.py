"""文件罗盘协议 · 资源索引 ref_index（characters/scenes/props 各一份）。

三层 manifest 的最底层：name → 落盘文件 + source/status。
操作 <project>/{characters,scenes,props}/ref_index.json。

纯逻辑、无 Qt，全单测。字段形状照 research §2.3。
用途：出图/出片前的「资源完备性闸门」——断点跳过 + 缺图阻断。
completeness_check 判定：status != ready 或落盘文件不存在 → 计入缺失。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

# ref_index.json 在 characters/scenes/props 目录下的固定文件名
REF_INDEX_FILENAME = "ref_index.json"

# status：ready 表示该 ref 已就绪可下游消费；其余（pending/...）视为未完备
READY_STATUS = "ready"
DEFAULT_STATUS = "pending"


@dataclass
class RefEntry:
    """单个资源条目：稳定名 → 落盘文件 + 来源 + 就绪状态。

    name：稳定引用名（如「女主」，下游 prompt 头部用 @女主_ref.png 引用）。
    path：相对项目（或所属子目录）的落盘文件路径。
    source：template | custom | ai-generated（来源，便于审批/派生）。
    status：ready | pending（断点续跑：ready 跳过、pending 待补）。
    """
    name: str
    path: str = ""
    source: str = ""
    status: str = DEFAULT_STATUS

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": self.path,
            "source": self.source,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RefEntry":
        d = d or {}
        return cls(
            name=str(d.get("name") or ""),
            path=str(d.get("path") or ""),
            source=str(d.get("source") or ""),
            status=str(d.get("status") or DEFAULT_STATUS),
        )


class RefIndex:
    """某一资源类（角色/场景/道具）的 ref_index.json 内存模型。"""

    def __init__(self) -> None:
        # 保序登记，便于稳定输出顺序
        self.entries: list[RefEntry] = []

    # ---- 增改查 ------------------------------------------------------

    def add(self, name: str, path: str,
            source: str = "", status: str = DEFAULT_STATUS) -> RefEntry:
        """登记/覆盖一个资源条目；同名覆盖（不重复登记）。"""
        existing = self.get(name)
        if existing is not None:
            existing.path = path
            existing.source = source
            existing.status = status
            return existing
        entry = RefEntry(name=name, path=path, source=source, status=status)
        self.entries.append(entry)
        return entry

    def get(self, name: str) -> Optional[RefEntry]:
        """按名取条目；不存在 → None。"""
        for e in self.entries:
            if e.name == name:
                return e
        return None

    def name_to_path(self) -> dict[str, str]:
        """name → path 映射（按登记顺序）。"""
        return {e.name: e.path for e in self.entries}

    # ---- 完备性闸门 --------------------------------------------------

    def completeness_check(
        self, base_dir: Optional[Union[str, Path]] = None
    ) -> list[str]:
        """返回缺失资源的 name 列表。

        判定为缺失：
        - status != ready；或
        - base_dir 给定且落盘文件不存在（path 解析相对 base_dir）。
        base_dir=None 时只看 status，不查文件存在（纯逻辑校验）。
        """
        base = Path(base_dir) if base_dir is not None else None
        missing: list[str] = []
        for e in self.entries:
            if e.status != READY_STATUS:
                missing.append(e.name)
                continue
            if base is not None:
                fp = base / e.path if not Path(e.path).is_absolute() else Path(e.path)
                if not fp.exists():
                    missing.append(e.name)
        return missing

    # ---- 序列化 ------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "schema_version": 1,
            "refs": [e.to_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "RefIndex":
        idx = cls()
        d = d or {}
        raw = d.get("refs")
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    idx.entries.append(RefEntry.from_dict(item))
        return idx


# ---- 落盘读写 ---------------------------------------------------------

def _resolve_path(path: Union[str, Path]) -> Path:
    """传目录则自动拼 ref_index.json；传文件则原样。"""
    p = Path(path)
    if p.is_dir() or p.suffix == "":
        return p / REF_INDEX_FILENAME
    return p


def load_ref_index(path: Union[str, Path]) -> RefIndex:
    """读 ref_index.json → RefIndex；缺失/坏 JSON/非 dict → 空索引不崩。"""
    p = _resolve_path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return RefIndex()
    if not isinstance(data, dict):
        return RefIndex()
    return RefIndex.from_dict(data)


def save_ref_index(idx: RefIndex, path: Union[str, Path]) -> Path:
    """落盘 ref_index.json：utf-8、不转义中文、缩进。"""
    p = _resolve_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(idx.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return p
