"""R1-T3 · RefIndex 单测（纯逻辑，无 Qt）。

操作 <project>/{characters,scenes,props}/ref_index.json，
记 name→落盘文件 + source/status，断点跳过。

覆盖：
- name→path 映射 round-trip（落盘再读回，字段一致）
- add(name,path,source,status)（含覆盖同名、默认 status）
- get(name) → 条目 / None
- completeness_check() → 缺失列表（status!=ready 或文件不存在）
- 坏 JSON / 缺文件 → 默认不崩
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from drama_shot_master.core.compass.ref_index import (
    REF_INDEX_FILENAME,
    RefEntry,
    RefIndex,
    load_ref_index,
    save_ref_index,
)


# ---- add / get 基本 ---------------------------------------------------

def test_add_and_get():
    idx = RefIndex()
    idx.add("女主", "characters/女主_ref.png", source="ai-generated", status="ready")
    e = idx.get("女主")
    assert e is not None
    assert e.name == "女主"
    assert e.path == "characters/女主_ref.png"
    assert e.source == "ai-generated"
    assert e.status == "ready"


def test_get_missing_returns_none():
    idx = RefIndex()
    assert idx.get("不存在") is None


def test_add_default_status_and_source():
    """不给 status/source → 走默认（status=pending）。"""
    idx = RefIndex()
    idx.add("男主", "characters/男主_ref.png")
    e = idx.get("男主")
    assert e is not None
    assert e.status == "pending"
    assert e.source == ""


def test_add_overwrites_same_name():
    idx = RefIndex()
    idx.add("女主", "old.png", status="pending")
    idx.add("女主", "new.png", status="ready")
    e = idx.get("女主")
    assert e.path == "new.png"
    assert e.status == "ready"
    # 不重复登记
    assert len(idx.entries) == 1


# ---- name→path 映射 ---------------------------------------------------

def test_name_to_path_mapping():
    idx = RefIndex()
    idx.add("女主", "characters/女主_ref.png", status="ready")
    idx.add("场景01", "scenes/scene_01_ref.png", status="ready")
    mapping = idx.name_to_path()
    assert mapping == {
        "女主": "characters/女主_ref.png",
        "场景01": "scenes/scene_01_ref.png",
    }


# ---- completeness_check ------------------------------------------------

def test_completeness_check_missing_when_status_not_ready():
    """status != ready → 计入缺失。"""
    idx = RefIndex()
    idx.add("女主", "女主_ref.png", status="ready")
    idx.add("男主", "男主_ref.png", status="pending")
    # 即便文件不在，先看 status；这里两文件都不存在但本测重点是 status
    missing = idx.completeness_check(base_dir=None)
    assert "男主" in missing
    # 女主 ready 但 base_dir=None 不查文件 → 不算缺失
    assert "女主" not in missing


def test_completeness_check_missing_when_file_absent(tmp_path: Path):
    """status=ready 但落盘文件不存在 → 计入缺失。"""
    idx = RefIndex()
    # 实际写一张存在的图
    (tmp_path / "女主_ref.png").write_bytes(b"\x89PNG")
    idx.add("女主", "女主_ref.png", status="ready")
    idx.add("男主", "男主_ref.png", status="ready")  # 文件不存在
    missing = idx.completeness_check(base_dir=tmp_path)
    assert missing == ["男主"]


def test_completeness_check_all_ready_returns_empty(tmp_path: Path):
    idx = RefIndex()
    (tmp_path / "a.png").write_bytes(b"\x89PNG")
    (tmp_path / "b.png").write_bytes(b"\x89PNG")
    idx.add("女主", "a.png", source="template", status="ready")
    idx.add("男主", "b.png", source="template", status="ready")
    assert idx.completeness_check(base_dir=tmp_path) == []


def test_completeness_check_no_base_dir_skips_file_existence():
    """base_dir=None → 只看 status，不查文件存在。"""
    idx = RefIndex()
    idx.add("女主", "女主_ref.png", status="ready")
    assert idx.completeness_check(base_dir=None) == []


# ---- load / save round-trip -------------------------------------------

def test_save_load_round_trip(tmp_path: Path):
    idx = RefIndex()
    idx.add("女主", "女主_ref.png", source="ai-generated", status="ready")
    idx.add("男主", "男主_ref.png", source="template", status="pending")

    path = tmp_path / "ref_index.json"
    save_ref_index(idx, path)
    assert path.exists()

    back = load_ref_index(path)
    assert back.get("女主").path == "女主_ref.png"
    assert back.get("女主").source == "ai-generated"
    assert back.get("女主").status == "ready"
    assert back.get("男主").status == "pending"
    assert back.name_to_path() == {
        "女主": "女主_ref.png",
        "男主": "男主_ref.png",
    }


def test_save_load_accepts_dir(tmp_path: Path):
    """load/save 接受目录路径（自动拼 ref_index.json）。"""
    idx = RefIndex()
    idx.add("女主", "女主_ref.png", status="ready")
    save_ref_index(idx, tmp_path)
    assert (tmp_path / REF_INDEX_FILENAME).exists()
    back = load_ref_index(tmp_path)
    assert back.get("女主") is not None


def test_save_writes_utf8(tmp_path: Path):
    idx = RefIndex()
    idx.add("女主", "女主_ref.png", status="ready")
    path = tmp_path / "ref_index.json"
    save_ref_index(idx, path)
    text = path.read_text(encoding="utf-8")
    assert "女主" in text  # 不转义中文
    data = json.loads(text)
    assert isinstance(data, dict)


# ---- 坏 JSON / 缺文件 → 默认不崩 --------------------------------------

def test_load_missing_file_returns_empty(tmp_path: Path):
    idx = load_ref_index(tmp_path / "nope.json")
    assert isinstance(idx, RefIndex)
    assert idx.entries == []


def test_load_bad_json_returns_empty(tmp_path: Path):
    path = tmp_path / "ref_index.json"
    path.write_text("{ not valid ]", encoding="utf-8")
    idx = load_ref_index(path)
    assert isinstance(idx, RefIndex)
    assert idx.entries == []


def test_load_non_dict_json_returns_empty(tmp_path: Path):
    path = tmp_path / "ref_index.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    idx = load_ref_index(path)
    assert isinstance(idx, RefIndex)
    assert idx.entries == []
