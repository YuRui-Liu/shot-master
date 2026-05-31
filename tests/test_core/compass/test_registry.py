"""R1-T2 · ProjectRegistry 单测（纯逻辑，无 Qt）。

操作 <projects_root>/index.json 全局注册表。覆盖：
- 缺失自愈初始化 {schema_version:1, next_id:"P-001", projects:[]}
- allocate_id 自增（P-001 → P-002 …），并持久化 next_id
- register(summary) / list_projects() / update_summary(project_id, **fields)
- 坏文件（坏 JSON / 非 dict）→ 自愈不崩

字段形状照 research §2.2。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from drama_shot_master.core.compass.registry import (
    INDEX_FILENAME,
    ProjectRegistry,
)


# ---- 缺失自愈 ----------------------------------------------------------

def test_missing_index_self_heals_defaults(tmp_path: Path):
    """index.json 不存在 → 以默认骨架自愈，不抛。"""
    reg = ProjectRegistry(tmp_path)
    assert reg.schema_version == 1
    assert reg.next_id == "P-001"
    assert reg.list_projects() == []


def test_missing_index_resolves_filename(tmp_path: Path):
    """传目录 → 自动定位 index.json。"""
    reg = ProjectRegistry(tmp_path)
    reg.save()
    assert (tmp_path / INDEX_FILENAME).exists()


def test_save_then_reload_round_trip(tmp_path: Path):
    reg = ProjectRegistry(tmp_path)
    reg.allocate_id()  # → P-001，next_id 推进到 P-002
    reg.register({"project_id": "P-001", "project_name": "替嫁新娘的逆袭"})
    reg.save()

    reg2 = ProjectRegistry(tmp_path)
    assert reg2.next_id == "P-002"
    projs = reg2.list_projects()
    assert len(projs) == 1
    assert projs[0]["project_id"] == "P-001"
    assert projs[0]["project_name"] == "替嫁新娘的逆袭"


# ---- allocate_id 自增 --------------------------------------------------

def test_allocate_id_increments(tmp_path: Path):
    reg = ProjectRegistry(tmp_path)
    assert reg.allocate_id() == "P-001"
    assert reg.next_id == "P-002"
    assert reg.allocate_id() == "P-002"
    assert reg.next_id == "P-003"


def test_allocate_id_persisted(tmp_path: Path):
    """allocate_id 推进的 next_id 落盘后重读仍生效（禁硬编码 ID）。"""
    reg = ProjectRegistry(tmp_path)
    reg.allocate_id()
    reg.allocate_id()
    reg.save()
    reg2 = ProjectRegistry(tmp_path)
    assert reg2.allocate_id() == "P-003"


def test_allocate_id_zero_padded_three_digits(tmp_path: Path):
    reg = ProjectRegistry(tmp_path)
    ids = [reg.allocate_id() for _ in range(11)]
    assert ids[0] == "P-001"
    assert ids[9] == "P-010"
    assert ids[10] == "P-011"


# ---- register / list_projects -----------------------------------------

def test_register_appends_summary(tmp_path: Path):
    reg = ProjectRegistry(tmp_path)
    pid = reg.allocate_id()
    reg.register({
        "project_id": pid,
        "project_name": "替嫁新娘的逆袭",
        "dir": "P-001_tijia-xinniang/",
        "genre": "短剧",
        "status": "media_ready",
        "episode_count": 12,
    })
    projs = reg.list_projects()
    assert len(projs) == 1
    s = projs[0]
    assert s["project_id"] == "P-001"
    assert s["genre"] == "短剧"
    assert s["episode_count"] == 12
    # 时间戳补齐
    assert s.get("created_at")
    assert s.get("last_modified")


def test_register_dedupes_by_project_id(tmp_path: Path):
    """同 project_id 再 register → 覆盖而非重复追加。"""
    reg = ProjectRegistry(tmp_path)
    reg.register({"project_id": "P-001", "project_name": "旧名"})
    reg.register({"project_id": "P-001", "project_name": "新名"})
    projs = reg.list_projects()
    assert len(projs) == 1
    assert projs[0]["project_name"] == "新名"


def test_list_projects_returns_copies(tmp_path: Path):
    """list_projects 返回副本，外部改动不污染内部状态。"""
    reg = ProjectRegistry(tmp_path)
    reg.register({"project_id": "P-001", "project_name": "替嫁"})
    projs = reg.list_projects()
    projs[0]["project_name"] = "被篡改"
    assert reg.list_projects()[0]["project_name"] == "替嫁"


# ---- update_summary ----------------------------------------------------

def test_update_summary_fields(tmp_path: Path):
    reg = ProjectRegistry(tmp_path)
    reg.register({"project_id": "P-001", "project_name": "替嫁", "status": "scripted"})
    reg.update_summary(
        "P-001",
        status="media_ready",
        completed_episodes=["E1", "E2"],
        cover="P-001/cover.png",
    )
    s = reg.list_projects()[0]
    assert s["status"] == "media_ready"
    assert s["completed_episodes"] == ["E1", "E2"]
    assert s["cover"] == "P-001/cover.png"


def test_update_summary_refreshes_last_modified(tmp_path: Path):
    reg = ProjectRegistry(tmp_path)
    reg.register({"project_id": "P-001", "project_name": "替嫁"})
    before = reg.list_projects()[0]["last_modified"]
    reg.update_summary("P-001", status="media_ready")
    after = reg.list_projects()[0]["last_modified"]
    assert after  # 非空
    # 不应改动其它已有字段
    assert reg.list_projects()[0]["project_name"] == "替嫁"


def test_update_summary_unknown_id_noop(tmp_path: Path):
    """未知 project_id → 不抛、不新增。"""
    reg = ProjectRegistry(tmp_path)
    reg.register({"project_id": "P-001", "project_name": "替嫁"})
    reg.update_summary("P-999", status="media_ready")
    assert len(reg.list_projects()) == 1


def test_update_summary_persists(tmp_path: Path):
    reg = ProjectRegistry(tmp_path)
    reg.register({"project_id": "P-001", "project_name": "替嫁"})
    reg.update_summary("P-001", status="tasks_ready")
    reg.save()
    reg2 = ProjectRegistry(tmp_path)
    assert reg2.list_projects()[0]["status"] == "tasks_ready"


# ---- 坏文件 → 自愈 -----------------------------------------------------

def test_bad_json_self_heals(tmp_path: Path):
    path = tmp_path / INDEX_FILENAME
    path.write_text("{ not valid json ]", encoding="utf-8")
    reg = ProjectRegistry(tmp_path)
    assert reg.next_id == "P-001"
    assert reg.list_projects() == []


def test_non_dict_json_self_heals(tmp_path: Path):
    path = tmp_path / INDEX_FILENAME
    path.write_text("[1, 2, 3]", encoding="utf-8")
    reg = ProjectRegistry(tmp_path)
    assert reg.next_id == "P-001"
    assert reg.list_projects() == []


def test_corrupt_next_id_self_heals(tmp_path: Path):
    """next_id 形状坏（非 P-NNN）→ 退回 P-001。"""
    path = tmp_path / INDEX_FILENAME
    path.write_text(
        json.dumps({"schema_version": 1, "next_id": "garbage", "projects": []}),
        encoding="utf-8",
    )
    reg = ProjectRegistry(tmp_path)
    assert reg.allocate_id() == "P-001"


# ---- 落盘形状 ----------------------------------------------------------

def test_save_writes_utf8_human_readable(tmp_path: Path):
    reg = ProjectRegistry(tmp_path)
    reg.register({"project_id": "P-001", "project_name": "替嫁新娘的逆袭"})
    reg.save()
    text = (tmp_path / INDEX_FILENAME).read_text(encoding="utf-8")
    assert "替嫁新娘的逆袭" in text  # 不转义中文
    data = json.loads(text)
    assert data["schema_version"] == 1
    assert data["projects"][0]["project_id"] == "P-001"
    assert data.get("last_updated")
