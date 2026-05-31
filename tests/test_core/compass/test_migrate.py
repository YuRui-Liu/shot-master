"""R1-T6 · migrate 单测（纯逻辑，无 Qt）。

把现有 project_dir（无 project.json 的平铺产物）升级为带 project.json 的总线项目。
覆盖：
- 扫描既有产物（创意.json / 剧本.json / 剧本_E1.md / 分镜_E1.json / prompts/E1/）
  → 推断 pipeline state（剧本→screenwriter completed、分镜→storyboard in_progress…）
- episodes：从 剧本.json 集索引 + 逐集文件派生路径/标题
- artifacts：idea/script_index + 存在的 ref_index 路径
- 生成 project.json（manifest.save_manifest）并登记进 registry
- 已有 project.json → 不覆盖（幂等）

原则「升级不推倒」：兼容现有命名/集 ID E1…，不改既有文件名。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from drama_shot_master.core.compass.manifest import (
    MANIFEST_FILENAME,
    ProjectManifest,
    load_manifest,
)
from drama_shot_master.core.compass.migrate import migrate_project_dir
from drama_shot_master.core.compass.registry import ProjectRegistry


# ---- 测试夹具：构造一个无 project.json 的现有项目 -----------------------

def _make_legacy_project(
    root: Path,
    *,
    with_script: bool = True,
    with_storyboard: bool = True,
    with_idea: bool = True,
    with_prompts: bool = True,
    with_characters: bool = False,
) -> Path:
    """造一个平铺产物的旧项目目录（无 project.json），返回项目根。"""
    pdir = root / "P-001_tijia-xinniang"
    pdir.mkdir(parents=True, exist_ok=True)

    if with_idea:
        (pdir / "创意.json").write_text(
            json.dumps({"title": "替嫁新娘的逆袭"}, ensure_ascii=False),
            encoding="utf-8",
        )

    if with_script:
        (pdir / "剧本.json").write_text(
            json.dumps(
                {
                    "title": "替嫁新娘的逆袭",
                    "episode_count": 2,
                    "episodes": [
                        {"id": "E1", "title": "替嫁", "summary": "..."},
                        {"id": "E2", "title": "反击", "summary": "..."},
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (pdir / "剧本_E1.md").write_text("# 第一集", encoding="utf-8")
        (pdir / "剧本_E2.md").write_text("# 第二集", encoding="utf-8")

    if with_storyboard:
        (pdir / "分镜_E1.json").write_text(
            json.dumps({"storyboard": [{"ai_image_prompt": "p"}]}, ensure_ascii=False),
            encoding="utf-8",
        )

    if with_prompts:
        pe1 = pdir / "prompts" / "E1"
        pe1.mkdir(parents=True, exist_ok=True)
        (pe1 / "shot001.txt").write_text("prompt 1", encoding="utf-8")

    if with_characters:
        cdir = pdir / "characters"
        cdir.mkdir(parents=True, exist_ok=True)
        (cdir / "ref_index.json").write_text(
            json.dumps({"schema_version": 1, "refs": []}, ensure_ascii=False),
            encoding="utf-8",
        )

    return pdir


# ---- 生成 project.json --------------------------------------------------

def test_migrate_creates_manifest_file(tmp_path: Path):
    pdir = _make_legacy_project(tmp_path)
    assert not (pdir / MANIFEST_FILENAME).exists()

    manifest = migrate_project_dir(pdir)

    assert isinstance(manifest, ProjectManifest)
    assert (pdir / MANIFEST_FILENAME).exists()


def test_migrate_infers_project_identity(tmp_path: Path):
    """从目录名/创意推断 project_id 与项目名。"""
    pdir = _make_legacy_project(tmp_path)
    manifest = migrate_project_dir(pdir)
    assert manifest.project_id == "P-001"
    assert manifest.project_name == "替嫁新娘的逆袭"


# ---- pipeline 推断 ------------------------------------------------------

def test_migrate_script_present_screenwriter_completed(tmp_path: Path):
    """有剧本 → screenwriter completed。"""
    pdir = _make_legacy_project(tmp_path)
    manifest = migrate_project_dir(pdir)
    assert manifest.stage_state("screenwriter") == "completed"


def test_migrate_storyboard_present_storyboard_in_progress(tmp_path: Path):
    """有分镜 → storyboard in_progress。"""
    pdir = _make_legacy_project(tmp_path)
    manifest = migrate_project_dir(pdir)
    assert manifest.stage_state("storyboard") == "in_progress"


def test_migrate_only_idea_screenwriter_in_progress(tmp_path: Path):
    """仅有创意无剧本 → screenwriter in_progress、storyboard pending。"""
    pdir = _make_legacy_project(
        tmp_path, with_script=False, with_storyboard=False, with_prompts=False
    )
    manifest = migrate_project_dir(pdir)
    assert manifest.stage_state("screenwriter") == "in_progress"
    assert manifest.stage_state("storyboard") == "pending"


def test_migrate_no_storyboard_stays_pending(tmp_path: Path):
    pdir = _make_legacy_project(tmp_path, with_storyboard=False, with_prompts=False)
    manifest = migrate_project_dir(pdir)
    assert manifest.stage_state("screenwriter") == "completed"
    assert manifest.stage_state("storyboard") == "pending"


# ---- episodes 推断 ------------------------------------------------------

def test_migrate_builds_episodes_from_index(tmp_path: Path):
    pdir = _make_legacy_project(tmp_path)
    manifest = migrate_project_dir(pdir)
    assert set(manifest.episodes) == {"E1", "E2"}
    assert manifest.episodes["E1"].title == "替嫁"
    assert manifest.episodes["E1"].script == "剧本_E1.md"
    # 只有 E1 有分镜
    assert manifest.episodes["E1"].storyboard == "分镜_E1.json"
    assert manifest.episodes["E2"].storyboard == ""


def test_migrate_episode_image_prompts_dir(tmp_path: Path):
    pdir = _make_legacy_project(tmp_path)
    manifest = migrate_project_dir(pdir)
    assert manifest.episodes["E1"].image_prompts.replace("\\", "/") == "prompts/E1/"


# ---- artifacts 推断 -----------------------------------------------------

def test_migrate_artifacts_idea_and_script_index(tmp_path: Path):
    pdir = _make_legacy_project(tmp_path)
    manifest = migrate_project_dir(pdir)
    assert manifest.artifacts.get("idea") == "创意.json"
    assert manifest.artifacts.get("script_index") == "剧本.json"


def test_migrate_artifacts_includes_existing_ref_index(tmp_path: Path):
    pdir = _make_legacy_project(tmp_path, with_characters=True)
    manifest = migrate_project_dir(pdir)
    chars = manifest.artifacts.get("characters", "").replace("\\", "/")
    assert chars == "characters/ref_index.json"


def test_migrate_artifacts_omits_missing_ref_index(tmp_path: Path):
    pdir = _make_legacy_project(tmp_path, with_characters=False)
    manifest = migrate_project_dir(pdir)
    assert "characters" not in manifest.artifacts


# ---- 登记进 registry ----------------------------------------------------

def test_migrate_registers_into_registry(tmp_path: Path):
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    pdir = _make_legacy_project(projects_root)
    reg = ProjectRegistry(projects_root)

    migrate_project_dir(pdir, registry=reg)

    projs = reg.list_projects()
    assert len(projs) == 1
    assert projs[0]["project_id"] == "P-001"
    assert projs[0]["project_name"] == "替嫁新娘的逆袭"


def test_migrate_without_registry_ok(tmp_path: Path):
    """不传 registry → 仅生成 project.json，不抛。"""
    pdir = _make_legacy_project(tmp_path)
    manifest = migrate_project_dir(pdir, registry=None)
    assert (pdir / MANIFEST_FILENAME).exists()
    assert manifest.project_id == "P-001"


# ---- 幂等：已有 project.json → 不覆盖 -----------------------------------

def test_migrate_idempotent_does_not_overwrite(tmp_path: Path):
    pdir = _make_legacy_project(tmp_path)

    # 首次迁移生成 project.json
    first = migrate_project_dir(pdir)
    # 人为篡改 manifest 标记后落盘，模拟已有自定义 manifest
    manifest_file = pdir / MANIFEST_FILENAME
    data = json.loads(manifest_file.read_text(encoding="utf-8"))
    data["project_name"] = "用户自定义名"
    manifest_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 再次迁移：不应覆盖
    second = migrate_project_dir(pdir)
    assert second.project_name == "用户自定义名"
    reloaded = load_manifest(pdir)
    assert reloaded.project_name == "用户自定义名"


def test_migrate_idempotent_does_not_double_register(tmp_path: Path):
    """已有 project.json 再迁移 → registry 不重复登记。"""
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    pdir = _make_legacy_project(projects_root)
    reg = ProjectRegistry(projects_root)

    migrate_project_dir(pdir, registry=reg)
    migrate_project_dir(pdir, registry=reg)

    assert len(reg.list_projects()) == 1
