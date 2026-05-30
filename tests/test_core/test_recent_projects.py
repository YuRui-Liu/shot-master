import json
from pathlib import Path
import pytest
from drama_shot_master.core.recent_projects import RecentProjectsManager


def test_load_empty_when_file_missing(tmp_path):
    mgr = RecentProjectsManager(tmp_path / "recent.json")
    assert mgr.load() == []


def test_push_creates_entry(tmp_path):
    mgr = RecentProjectsManager(tmp_path / "recent.json")
    mgr.push(str(tmp_path), "Alpha")
    projects = mgr.load()
    assert len(projects) == 1
    assert projects[0]["path"] == str(tmp_path)
    assert projects[0]["name"] == "Alpha"


def test_push_deduplicates_by_path(tmp_path):
    mgr = RecentProjectsManager(tmp_path / "recent.json")
    mgr.push(str(tmp_path), "Alpha")
    mgr.push(str(tmp_path), "Alpha v2")
    projects = mgr.load()
    assert len(projects) == 1
    assert projects[0]["name"] == "Alpha v2"


def test_push_trims_to_max(tmp_path):
    mgr = RecentProjectsManager(tmp_path / "recent.json")
    for i in range(10):
        sub = tmp_path / f"proj_{i}"
        sub.mkdir()
        mgr.push(str(sub), f"Project {i}")
    assert len(mgr.load()) == RecentProjectsManager.MAX


def test_most_recent_first(tmp_path):
    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    old_dir.mkdir()
    new_dir.mkdir()
    mgr = RecentProjectsManager(tmp_path / "recent.json")
    mgr.push(str(old_dir), "Old")
    mgr.push(str(new_dir), "New")
    projects = mgr.load()
    assert projects[0]["path"] == str(new_dir)


def test_load_skips_missing_paths(tmp_path):
    mgr = RecentProjectsManager(tmp_path / "recent.json")
    mgr.push(str(tmp_path), "exists")
    mgr.push("/nonexistent/path/xyz", "missing")
    projects = mgr.load()
    assert all(p["path"] == str(tmp_path) for p in projects)
    assert len(projects) == 1


def test_remove_deletes_entry(tmp_path):
    mgr = RecentProjectsManager(tmp_path / "recent.json")
    mgr.push(str(tmp_path), "Alpha")
    mgr.remove(str(tmp_path))
    assert mgr.load() == []


def test_push_without_name_uses_dirname(tmp_path):
    drama_dir = tmp_path / "MyDrama"
    drama_dir.mkdir()
    mgr = RecentProjectsManager(tmp_path / "recent.json")
    mgr.push(str(drama_dir))
    projects = mgr.load()
    assert projects[0]["name"] == "MyDrama"
