"""R1-T4 · compass.paths 单测（纯逻辑，无 Qt）。

覆盖：
- 项目根 / 各产物路径拼装（兼容 创意.json/剧本.json/剧本_E1.md/分镜_E1.json/prompts/E1/）
- 标准目录树子目录（characters/scenes/props/assets/shots/clips/soundtrack/exports/归档）
- split_unit ∈ {episode,segment,shot} 切换时 ID 前缀（E/SEG/S）与子目录正确
- 三位补零 shot001 / unit_id 拼装
- 复用/包装 screenwriter_agent.core.paths，不重复定义
"""
from __future__ import annotations

from pathlib import Path

import pytest

from drama_shot_master.core.compass import paths as cpaths


# ---- 项目根布局 -------------------------------------------------------

def test_project_dir_under_root_with_id_slug(tmp_path: Path):
    """项目目录 = <root>/{ID}_{slug}/。"""
    root = tmp_path
    d = cpaths.project_dir(root, "P-006", "tijia-xinniang")
    assert d == root / "P-006_tijia-xinniang"


def test_project_dir_no_slug_uses_id_only(tmp_path: Path):
    """无 slug 时目录名仅 ID。"""
    d = cpaths.project_dir(tmp_path, "P-006", "")
    assert d == tmp_path / "P-006"


def test_registry_index_path(tmp_path: Path):
    """全局注册表 index.json 在 root 下。"""
    assert cpaths.registry_index_path(tmp_path) == tmp_path / "index.json"


def test_manifest_path(tmp_path: Path):
    """项目清单 project.json 在 project_dir 下。"""
    pd = tmp_path / "P-006_x"
    assert cpaths.manifest_path(pd) == pd / "project.json"


# ---- 标准子目录树 -----------------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("characters", "characters"),
    ("scenes", "scenes"),
    ("props", "props"),
    ("assets", "assets"),
    ("soundtrack", "soundtrack"),
    ("exports", "exports"),
])
def test_subdir(tmp_path: Path, name: str, expected: str):
    pd = tmp_path / "P-006_x"
    assert getattr(cpaths, f"{name}_dir")(pd) == pd / expected


def test_archive_dir_chinese(tmp_path: Path):
    """归档目录用中文名 归档/。"""
    pd = tmp_path / "P-006_x"
    assert cpaths.archive_dir(pd) == pd / "归档"


def test_ref_index_path_for_resource_kind(tmp_path: Path):
    """characters/scenes/props 各自的 ref_index.json。"""
    pd = tmp_path / "P-006_x"
    assert cpaths.ref_index_path(pd, "characters") == pd / "characters" / "ref_index.json"
    assert cpaths.ref_index_path(pd, "scenes") == pd / "scenes" / "ref_index.json"
    assert cpaths.ref_index_path(pd, "props") == pd / "props" / "ref_index.json"


def test_ref_index_path_rejects_unknown_kind(tmp_path: Path):
    pd = tmp_path / "P-006_x"
    with pytest.raises(ValueError):
        cpaths.ref_index_path(pd, "unknown")


# ---- 兼容现有产物路径（包装 screenwriter_agent.core.paths） -----------

def test_idea_path_compat(tmp_path: Path):
    pd = tmp_path / "P-006_x"
    assert cpaths.idea_path(pd) == pd / "创意.json"


def test_script_index_path_compat(tmp_path: Path):
    pd = tmp_path / "P-006_x"
    assert cpaths.script_index_path(pd) == pd / "剧本.json"


def test_script_episode_path_compat(tmp_path: Path):
    pd = tmp_path / "P-006_x"
    assert cpaths.script_unit_path(pd, "E1") == pd / "剧本_E1.md"


def test_storyboard_episode_path_compat(tmp_path: Path):
    pd = tmp_path / "P-006_x"
    assert cpaths.storyboard_unit_path(pd, "E1") == pd / "分镜_E1.json"


def test_image_prompts_dir_compat(tmp_path: Path):
    pd = tmp_path / "P-006_x"
    assert cpaths.image_prompts_dir(pd, "E1") == pd / "prompts" / "E1"


def test_video_audio_prompts_dir_compat(tmp_path: Path):
    pd = tmp_path / "P-006_x"
    assert cpaths.video_prompts_dir(pd, "E1") == pd / "video_prompts" / "E1"
    assert cpaths.audio_prompts_dir(pd, "E1") == pd / "audio_prompts" / "E1"


def test_shots_and_clips_dir(tmp_path: Path):
    """② 分镜底图 shots/E1/，③ 视频碎片 clips/E1/。"""
    pd = tmp_path / "P-006_x"
    assert cpaths.shots_dir(pd, "E1") == pd / "shots" / "E1"
    assert cpaths.clips_dir(pd, "E1") == pd / "clips" / "E1"


# ---- split_unit → ID 前缀 ---------------------------------------------

@pytest.mark.parametrize("split_unit,prefix", [
    ("episode", "E"),
    ("segment", "SEG"),
    ("shot", "S"),
])
def test_unit_prefix(split_unit: str, prefix: str):
    assert cpaths.unit_prefix(split_unit) == prefix


def test_unit_prefix_unknown_raises():
    with pytest.raises(ValueError):
        cpaths.unit_prefix("take-unknown")


@pytest.mark.parametrize("split_unit,n,expected", [
    ("episode", 1, "E1"),
    ("episode", 12, "E12"),
    ("segment", 1, "SEG01"),
    ("segment", 12, "SEG12"),
    ("shot", 1, "S001"),
    ("shot", 12, "S012"),
])
def test_make_unit_id(split_unit: str, n: int, expected: str):
    """单位 ID 拼装：episode 不补零、segment 两位补零、shot 三位补零。"""
    assert cpaths.make_unit_id(split_unit, n) == expected


# ---- 三位补零 shotNNN --------------------------------------------------

@pytest.mark.parametrize("n,expected", [
    (1, "shot001"),
    (7, "shot007"),
    (12, "shot012"),
    (123, "shot123"),
])
def test_shot_filename_stem_zero_pad(n: int, expected: str):
    assert cpaths.shot_stem(n) == expected


def test_shot_image_path_zero_pad(tmp_path: Path):
    """shots/E1/shot001.png 三位补零。"""
    pd = tmp_path / "P-006_x"
    assert cpaths.shot_image_path(pd, "E1", 1) == pd / "shots" / "E1" / "shot001.png"
    assert cpaths.shot_image_path(pd, "E1", 12) == pd / "shots" / "E1" / "shot012.png"


def test_shot_prompt_path_zero_pad(tmp_path: Path):
    """prompts/E1/shot001.txt 三位补零。"""
    pd = tmp_path / "P-006_x"
    assert cpaths.shot_prompt_path(pd, "E1", 1) == pd / "prompts" / "E1" / "shot001.txt"


# ---- split_unit 驱动子目录（分片单位感知） ----------------------------

def test_unit_dir_switches_with_split_unit(tmp_path: Path):
    """split_unit 切换时，逐单位产物子目录用对应 unit_id。"""
    pd = tmp_path / "P-006_x"
    # episode → E1
    assert cpaths.image_prompts_dir(pd, cpaths.make_unit_id("episode", 1)) == pd / "prompts" / "E1"
    # segment → SEG01
    assert cpaths.image_prompts_dir(pd, cpaths.make_unit_id("segment", 1)) == pd / "prompts" / "SEG01"
    # shot → S001
    assert cpaths.image_prompts_dir(pd, cpaths.make_unit_id("shot", 1)) == pd / "prompts" / "S001"
