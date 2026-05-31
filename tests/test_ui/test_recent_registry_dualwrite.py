"""B3 · recent_projects.push 双写 registry（双轨并存）。

push() 在写 recent_projects.json 之外，同步登记到项目所在 projects_root 的
全局注册表 index.json（compass.registry）。recent.json 原行为保留；registry
操作 try/except 降级不崩，不影响 recent 主流程。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from drama_shot_master.core.recent_projects import RecentProjectsManager
from drama_shot_master.core.compass.registry import ProjectRegistry


def _make_project_dir(projects_root: Path, dir_name: str) -> Path:
    """在 projects_root 下造一个项目目录。"""
    p = projects_root / dir_name
    p.mkdir(parents=True, exist_ok=True)
    return p


def test_push_writes_recent_and_registry(tmp_path: Path) -> None:
    """push 后：recent.json 有记录，且项目所在 projects_root 的 registry 也有对应项。"""
    settings_dir = tmp_path / "cfg"
    settings_dir.mkdir()
    mgr = RecentProjectsManager(settings_dir / "recent_projects.json")

    projects_root = tmp_path / "projects"
    proj = _make_project_dir(projects_root, "P-007_demo")

    mgr.push(str(proj), name="演示剧")

    # recent.json 原行为保留
    recent = mgr.load()
    assert any(Path(e["path"]) == proj for e in recent)
    assert recent[0]["name"] == "演示剧"

    # registry 双写：projects_root/index.json 出现该项目
    index_file = projects_root / "index.json"
    assert index_file.is_file()
    reg = ProjectRegistry(index_file)
    listed = reg.list_projects()
    assert len(listed) >= 1
    # project_id 取自目录前缀 P-007
    assert any(s.get("project_id") == "P-007" for s in listed)


def test_push_allocates_id_when_dir_has_no_prefix(tmp_path: Path) -> None:
    """目录名无 P-NNN 前缀 → registry 仍登记一项（allocate_id 补建），不漂移。"""
    mgr = RecentProjectsManager(tmp_path / "cfg" / "recent_projects.json")
    projects_root = tmp_path / "projects"
    proj = _make_project_dir(projects_root, "无前缀项目")

    mgr.push(str(proj))

    reg = ProjectRegistry(projects_root / "index.json")
    listed = reg.list_projects()
    assert len(listed) == 1
    # 必有一个非空 project_id（allocate_id 分配，形如 P-001）
    assert listed[0].get("project_id")


def test_push_survives_registry_failure(tmp_path: Path, monkeypatch) -> None:
    """registry 抛错时，recent.json 仍正常写入（降级不崩，主流程不受影响）。"""
    mgr = RecentProjectsManager(tmp_path / "cfg" / "recent_projects.json")
    projects_root = tmp_path / "projects"
    proj = _make_project_dir(projects_root, "P-001_x")

    # 让 registry 同步整段抛错
    import drama_shot_master.core.recent_projects as rp

    def _boom(*a, **k):
        raise RuntimeError("registry boom")

    monkeypatch.setattr(rp.RecentProjectsManager, "_sync_registry", _boom)

    # 不应抛出
    mgr.push(str(proj), name="容错剧")

    recent = mgr.load()
    assert any(Path(e["path"]) == proj for e in recent)
    assert recent[0]["name"] == "容错剧"


def test_push_updates_existing_registry_entry(tmp_path: Path) -> None:
    """同一项目重复 push → registry 不重复追加（register 覆盖/update_summary）。"""
    mgr = RecentProjectsManager(tmp_path / "cfg" / "recent_projects.json")
    projects_root = tmp_path / "projects"
    proj = _make_project_dir(projects_root, "P-002_dup")

    mgr.push(str(proj), name="第一次")
    mgr.push(str(proj), name="第二次")

    reg = ProjectRegistry(projects_root / "index.json")
    listed = [s for s in reg.list_projects() if s.get("project_id") == "P-002"]
    assert len(listed) == 1
