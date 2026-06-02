"""内容资产端点：题材模板 + 风格圣经 + 资源库 ref_index。

handler 仅调用 core/genre_templates 与 core/style_bible，返回其原始结构
（与 skills 路由调用 core/skill_templates 同构）——后端逻辑在 core，路由只做
HTTP 封装。

ref_index 段（角色/场景/道具）读写走 core/compass.ref_index + compass.paths，
与原 PySide6 asset_library_page 同源契约（每条 ref = name/path/source/status）。
- 读：GET /assets/refs?project=<dir> → 三类分组（无则空结构，降级不崩）。
- 写：PUT /assets/refs（整体落盘）/ POST /assets/refs/update（按条改字段）。
- 提取：POST /assets/refs/extract → 调 entity_extractor 从剧本填充三类名单。
- 生成：POST /assets/refs/generate → 生成单条 ref 图（可注入 provider 工厂）。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import json as _json

from drama_shot_master.core import genre_templates, style_bible
from drama_shot_master.core.compass import paths as _paths
from drama_shot_master.core.compass.manifest import load_manifest
from drama_shot_master.core.compass.ref_index import (
    READY_STATUS,
    RefIndex,
    load_ref_index,
    save_ref_index,
)
from drama_shot_master.services import entity_extractor

router = APIRouter(prefix="/assets")

# 资源库三类（与 ref_index 子目录 / paths.RESOURCE_KINDS 一致）
_KINDS = _paths.RESOURCE_KINDS  # ("characters", "scenes", "props")

# 提取/生成默认来源标记（对齐 RefEntry.source 语义：ai-generated）
_AI_SOURCE = "ai-generated"

# 角色 ref 图约束：角色生成的是「三视图设计图」（正/侧/背），纯色/无背景全身参考，
# 供后续出图作角色一致性参照。场景/道具类不加此约束（它们就是要带场景）。
_CHARACTER_TURNAROUND_HINT = (
    "three-view character design sheet, character turnaround, "
    "front side back views, full body reference, "
    "plain white neutral background, no scene background, no environment, "
    "consistent character design"
)


def _augment_prompt_for_kind(prompt: str, kind: str) -> str:
    """按资源种类增广提示词。

    characters：追加三视图/无背景全身参考约束（避免与场景类混在一起）；
    scenes/props：原样返回（不加角色约束）。
    """
    if kind == "characters":
        return f"{prompt}, {_CHARACTER_TURNAROUND_HINT}"
    return prompt


def _resolve_project_style_id(project_dir: Path) -> str:
    """解析项目当前风格 style_id（供 ref 生成注入风格圣经）。

    单一可信源优先级（对齐 screenwriter_client / overview_page 同源契约）：
      1) project.json（manifest）的 style_bible.ref
      2) 回退 创意.json 的 input.style_bible.ref
    都没有则返回空串（无风格 → 生成 prompt 原样，不注入）。
    """
    # 1) project.json.style_bible.ref（load_manifest 缺失/坏 JSON 不崩）
    try:
        manifest = load_manifest(project_dir)
        sb = manifest.style_bible
        if isinstance(sb, dict):
            ref = (sb.get("ref") or "").strip()
            if ref:
                return ref
    except Exception:  # noqa: BLE001 manifest 读失败 → 走回退
        pass

    # 2) 回退 创意.json input.style_bible.ref
    try:
        idea_path = project_dir / "创意.json"
        data = _json.loads(idea_path.read_text(encoding="utf-8"))
        inp = (data or {}).get("input") or {}
        sb = inp.get("style_bible") or {}
        if isinstance(sb, dict):
            ref = (sb.get("ref") or "").strip()
            if ref:
                return ref
    except (FileNotFoundError, OSError, ValueError, AttributeError):
        pass

    return ""


def _inject_project_style(prompt: str, project_dir: Path) -> str:
    """把项目风格圣经注入 ref 生成 prompt（ref 阶段：含 ref_fingerprint）。

    根因修复：原 /refs/generate 只加角色三视图约束、不注入项目 style_bible，
    导致出图用 provider 默认风格（如默认 2D）而非项目设定（如电影冷调）。
    这里读项目 style_id（manifest → 创意.json 回退），用 style_bible.get_style
    解析风格实体，再 inject_style_prompt(stage='ref')：
      base_prompt → ref_fingerprint(中性平光锁一致性) → prompt_suffix → negative_suffix。
    无风格（空 id / 未知 id）→ 原样返回 prompt（降级不崩）。
    """
    style_id = _resolve_project_style_id(project_dir)
    if not style_id:
        return prompt
    style = style_bible.get_style(style_id)
    if not style:
        return prompt
    return style_bible.inject_style_prompt(prompt, style, stage="ref")


# ---------- 题材模板 ----------

@router.get("/genres")
def list_genres_route():
    """返回全部题材 id（读 index.json 登记表）。"""
    return {"genres": genre_templates.list_genres()}


@router.get("/genres/detail")
def list_genres_detail_route():
    """题材卡片明细：对每个 id 取 display_name + 一句话定位 + 爽点权重。

    用于题材弹窗卡片展示。单个模板加载/解析失败则跳过该条（容错不崩）。
    返回 {genres:[{genre_id, display_name, one_liner, satisfaction_weights}]}。
    """
    out: list[dict] = []
    for gid in genre_templates.list_genres():
        try:
            t = genre_templates.load_genre(gid)
        except Exception:  # noqa: BLE001 单个加载失败跳过不崩
            continue
        identity = t.get("identity") or {}
        out.append({
            "genre_id": t.get("genre_id", gid),
            "display_name": t.get("display_name", gid),
            "one_liner": (identity.get("one_liner") if isinstance(identity, dict) else "") or "",
            "satisfaction_weights": t.get("satisfaction_weights") or {},
        })
    return {"genres": out}


@router.get("/genre")
def genre_detail_route(id: str):
    """单题材模板（yaml -> dict 原结构）。未知 id → 404、空 id → 400。"""
    if not id or not id.strip():
        raise HTTPException(status_code=400, detail="id 不能为空")
    try:
        return genre_templates.load_genre(id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"题材模板不存在: {id}")


# ---------- 风格圣经 ----------

@router.get("/styles")
def list_styles_route():
    """返回全局风格库原始 dict（含 schema_version/default_style_id/styles）。"""
    return style_bible.load_styles()


@router.get("/style")
def style_detail_route(id: str):
    """按 style_id 解析单条风格实体。未知 id → 404、空 id → 400。"""
    if not id or not id.strip():
        raise HTTPException(status_code=400, detail="id 不能为空")
    style = style_bible.get_style(id)
    if style is None:
        raise HTTPException(status_code=404, detail=f"风格不存在: {id}")
    return style


# ---------- 资源库 ref_index（角色/场景/道具） ----------

# 可注入：测试替换为假 provider 工厂（避免触网 / 依赖 API key）。
# 与 imggen 同构：cfg -> provider，provider.generate(prompt, references, *, size, n) -> list[bytes]。
_provider_factory = None  # 默认惰性构造（见 _build_provider），便于测试 monkeypatch


def _load_cfg():
    from drama_shot_master.config import load_config
    return load_config()


def _build_provider(cfg):
    """构造出图 provider；默认复用 providers.image_gen.make_image_provider。

    抽成函数便于测试 monkeypatch `_provider_factory`。需 API key/网络，
    故仅在 /refs/generate 真正调用时构造。
    """
    if _provider_factory is not None:
        return _provider_factory(cfg)
    from drama_shot_master.providers.image_gen import make_image_provider
    return make_image_provider(cfg)


def _project_dir(project: str) -> Path:
    """校验并解析项目目录；空 → 400、不存在 → 404。"""
    raw = (project or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="project 不能为空")
    p = Path(raw)
    if not p.is_dir():
        raise HTTPException(status_code=404, detail=f"项目目录不存在: {raw}")
    return p


def _load_kind(project_dir: Path, kind: str) -> RefIndex:
    """读某类 ref_index；无文件/坏 JSON → 空索引不崩。"""
    return load_ref_index(_paths.ref_index_path(project_dir, kind))


class RefEntryModel(BaseModel):
    name: str
    path: str = ""
    source: str = ""
    status: str = "pending"


class RefGroupModel(BaseModel):
    refs: list[RefEntryModel] = []


def _index_to_group(idx: RefIndex) -> dict:
    """RefIndex → {"refs": [条目 dict...]}（对齐 ref_index.json 结构去掉版本壳）。"""
    return {"refs": [e.to_dict() for e in idx.entries]}


@router.get("/refs")
def get_refs_route(project: str):
    """读项目三类 ref_index（角色/场景/道具分组）。无则各返回空 refs，不崩。"""
    pdir = _project_dir(project)
    return {kind: _index_to_group(_load_kind(pdir, kind)) for kind in _KINDS}


class PutRefsBody(BaseModel):
    project: str
    # kind -> 该类条目列表（缺的类不动；只覆盖给到的类）
    refs: dict[str, list[RefEntryModel]] = {}


@router.put("/refs")
def put_refs_route(body: PutRefsBody):
    """整体落盘 ref_index：按 kind 覆盖。未知 kind → 400。返回各类写入条目数。"""
    pdir = _project_dir(body.project)
    written: dict[str, int] = {}
    for kind, entries in body.refs.items():
        if kind not in _KINDS:
            raise HTTPException(
                status_code=400, detail=f"未知资源种类: {kind}")
        idx = RefIndex()
        for e in entries:
            name = (e.name or "").strip()
            if not name:
                continue
            idx.add(name, e.path or "", source=e.source or "",
                    status=e.status or "pending")
        save_ref_index(idx, _paths.ref_index_path(pdir, kind))
        written[kind] = len(idx.entries)
    return {"ok": True, "written": written}


class UpdateRefBody(BaseModel):
    project: str
    kind: str
    # 用 entity_id 定位（这里以 name 作稳定键，对齐 RefEntry 同名覆盖语义）
    entity_id: str
    # 可改字段（省略则保留原值）
    path: str | None = None
    source: str | None = None
    status: str | None = None


@router.post("/refs/update")
def update_ref_route(body: UpdateRefBody):
    """按条改一个 ref 的字段（path/source/status）。

    定位键 entity_id = ref name（与 RefEntry 同名覆盖语义一致）。
    条目不存在则新建（path 默认空、status 默认 pending），便于先登记后补图。
    未知 kind → 400、无项目 → 404。
    """
    if body.kind not in _KINDS:
        raise HTTPException(status_code=400, detail=f"未知资源种类: {body.kind}")
    name = (body.entity_id or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="entity_id 不能为空")
    pdir = _project_dir(body.project)
    path = _paths.ref_index_path(pdir, body.kind)
    idx = load_ref_index(path)
    entry = idx.get(name)
    if entry is None:
        entry = idx.add(name, "", source="", status="pending")
    if body.path is not None:
        entry.path = body.path
    if body.source is not None:
        entry.source = body.source
    if body.status is not None:
        entry.status = body.status
    save_ref_index(idx, path)
    return {"ok": True, "entry": entry.to_dict()}


class ExtractBody(BaseModel):
    project: str
    # 可直接喂剧本文本；省略则尝试读项目内剧本（降级为空）
    script_text: str = ""


def _read_project_script(project_dir: Path) -> str:
    """尽力读项目剧本文本供提取用；读不到 → 空串（上层降级返回空名单）。

    优先逐集剧本 剧本_*.md 合并；无则空（不抛，符合 extractor 全降级原则）。
    """
    chunks: list[str] = []
    try:
        for md in sorted(project_dir.glob("剧本_*.md")):
            try:
                chunks.append(md.read_text(encoding="utf-8"))
            except OSError:
                continue
    except OSError:
        return ""
    return "\n\n".join(chunks)


@router.post("/refs/extract")
def extract_refs_route(body: ExtractBody):
    """从剧本提取三类实体名单，合并填充 ref_index（幂等：同名不重复，保留原条目）。

    新名以 source=ai-generated / status=pending 登记（待生成/补图）。
    provider 未配置/抽取失败 → 名单为空，不改盘、不崩。返回各类新增数。
    """
    pdir = _project_dir(body.project)
    script_text = body.script_text or _read_project_script(pdir)

    extracted = entity_extractor.extract_entities(
        script_text, cfg=_safe_cfg(), work_dir=str(pdir))

    added: dict[str, int] = {}
    for kind in _KINDS:
        names = extracted.get(kind) or []
        path = _paths.ref_index_path(pdir, kind)
        idx = load_ref_index(path)
        new_count = 0
        for name in names:
            if idx.get(name) is None:
                idx.add(name, "", source=_AI_SOURCE, status="pending")
                new_count += 1
        if new_count:
            save_ref_index(idx, path)
        added[kind] = new_count
    return {"ok": True, "added": added,
            "refs": {kind: _index_to_group(_load_kind(pdir, kind))
                     for kind in _KINDS}}


def _safe_cfg():
    """读配置；失败 → None（extractor 接受 None 并降级）。"""
    try:
        return _load_cfg()
    except Exception:  # noqa: BLE001 配置读失败不应阻断提取（降级空名单）
        return None


class GenerateRefBody(BaseModel):
    project: str
    kind: str
    entity_id: str  # = ref name
    prompt: str = ""
    size: str = "1024x1024"


def _kind_dir(project_dir: Path, kind: str) -> Path:
    """某类落盘子目录（characters/scenes/props）。"""
    return project_dir / kind


@router.post("/refs/generate")
def generate_ref_route(body: GenerateRefBody):
    """生成单条 ref 图：调出图 provider → 落盘 <kind>/<name>_ref.<ext> → 更新条目。

    成功：path 写相对项目的子目录路径、status=ready、source=ai-generated。
    provider 未配置/无 key/网络失败 → 500（不静默假成功，便于前端提示）。
    未知 kind → 400、无项目 → 404、空 entity_id → 400。
    """
    if body.kind not in _KINDS:
        raise HTTPException(status_code=400, detail=f"未知资源种类: {body.kind}")
    name = (body.entity_id or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="entity_id 不能为空")
    pdir = _project_dir(body.project)

    index_path = _paths.ref_index_path(pdir, body.kind)
    idx = load_ref_index(index_path)
    entry = idx.get(name)
    # 提示词：显式优先，否则用名字兜底（让 provider 至少有输入）
    prompt = (body.prompt or "").strip() or name
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt 与 entity_id 均为空")
    # 角色类注入三视图/无背景约束；场景/道具原样
    prompt = _augment_prompt_for_kind(prompt, body.kind)
    # 注入项目风格圣经（ref 阶段：含视觉指纹），使 ref 图与项目设定的电影/2D/3D 风格一致
    prompt = _inject_project_style(prompt, pdir)

    cfg = _safe_cfg()
    if cfg is None:
        raise HTTPException(status_code=500, detail="配置读取失败，无法初始化出图 provider")
    try:
        provider = _build_provider(cfg)
        images = provider.generate(prompt, [], size=body.size, n=1)
    except Exception as e:  # noqa: BLE001 provider 失败 → 500 透出
        raise HTTPException(status_code=500, detail=f"生成失败: {e}")

    if not images:
        raise HTTPException(status_code=500, detail="provider 未返回图像")

    out_dir = _kind_dir(pdir, body.kind)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{name}_ref.png"
    data = images[0]
    if isinstance(data, str):
        # 兼容返回路径的 provider：原样记录
        rel_path = data
    else:
        out_path.write_bytes(data)
        # path 记相对项目目录（与 PySide6 读法一致：相对 base_dir 解析）
        rel_path = str(out_path.relative_to(pdir)).replace("\\", "/")

    if entry is None:
        entry = idx.add(name, rel_path, source=_AI_SOURCE, status=READY_STATUS)
    else:
        entry.path = rel_path
        entry.source = _AI_SOURCE
        entry.status = READY_STATUS
    save_ref_index(idx, index_path)
    return {"ok": True, "entry": entry.to_dict(), "output": str(out_path)}
