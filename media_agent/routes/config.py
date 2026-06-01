"""设置端点：GET /config 读当前设置 / PUT /config 落盘。纯逻辑、无 Qt。

读写走 drama_shot_master.config.load_config() —— 与 UI 设置页同源（仓库根
settings.json）。GET 只回传设置页用到的字段（含敏感项以便回填表单，本地单机工具）；
PUT 把 body 直接 update_settings(**body) 落盘。
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from drama_shot_master.config import load_config

router = APIRouter(prefix="/config")


# GET /config 回传字段白名单（设置页 sections 用到的）：平台核心 / 出图 / 配音 /
# 配乐 / 翻译 / 编剧 / 流程锁 / 项目根 等。
_EXPOSE_FIELDS = (
    # RunningHub（出图/视频/配音/配乐共享平台）
    "runninghub_api_key",
    "runninghub_workflow_id",
    "runninghub_base_url",
    "runninghub_template_path",
    # LLM 平台（跨功能共享）
    "llm_providers",
    "current_provider",
    "current_model",
    # 出图
    "imggen_provider",
    "imggen_base_url",
    "imggen_model",
    "imggen_api_key",
    "imggen_output_dir",
    "imggen_watermark",
    # 配音
    "dub_workflow_ids",
    "dub_output_dir",
    "dub_sampling",
    # 配乐
    "soundtrack_workflow_id",
    "soundtrack_output_dir",
    "soundtrack_seeds_count",
    "soundtrack_crossfade",
    "soundtrack_fade_out",
    # 翻译
    "deeplx_url",
    "current_translator",
    "tencent_translator_secret_id",
    "tencent_translator_secret_key",
    "tencent_translator_region",
    "tencent_translator_project_id",
    # 帧提示词优化
    "refine_base_url",
    "refine_api_key",
    "refine_model",
    "refine_provider",
    # 编剧
    "screenwriter_agent_port",
    "screenwriter_llm_api_key",
    "screenwriter_llm_base_url",
    "screenwriter_models",
    "screenwriter_project_root",
    "screenwriter_stage_assignments",
    "screenwriter_provider",
    "prompts_default_grid",
    # 视频生成 Workflow ID 表（LTX2.3 导演台等；切界面回填靠它）
    "workflow_ids",
    # 流程锁 / 项目根
    "pipeline_lock_enabled",
    "comfyui_url",
)


def _config_to_dict() -> dict:
    """把 load_config() 的设置页相关字段拍成 dict。

    额外暴露 projects_root（取 screenwriter_project_root 别名），方便概览/新建页消费。
    """
    cfg = load_config()
    out: dict = {}
    for f in _EXPOSE_FIELDS:
        out[f] = getattr(cfg, f, None)
    out["projects_root"] = getattr(cfg, "screenwriter_project_root", "") or ""
    return out


class ConfigBody(BaseModel):
    """PUT /config —— 任意设置字段透传给 update_settings(**body)。"""

    model_config = ConfigDict(extra="allow")


@router.get("")
def get_config():
    """返回当前设置（设置页用到的字段）。"""
    return _config_to_dict()


@router.put("")
def put_config(body: ConfigBody):
    """把 body 字段落盘到 settings.json，返回 {ok:true}。

    只接受 Config dataclass 已有的属性（update_settings 内部 hasattr 过滤）。
    """
    payload = body.model_dump(exclude_unset=True)
    payload.pop("projects_root", None)  # 非 Config 字段，update_settings 会忽略但显式剔除更干净
    cfg = load_config()
    # workflow_ids 是多界面共享的 dict（director_v3 / LTX2.3 导演台 各占一键）：
    # 前端常只 PUT 自己那一键，若整体替换会丢掉其它键。这里做浅合并——
    # 把当前盘上的表与 body 给到的键合并后再落盘（update_settings 仍是整体写）。
    incoming_workflow_ids = payload.get("workflow_ids")
    if isinstance(incoming_workflow_ids, dict):
        merged = dict(getattr(cfg, "workflow_ids", None) or {})
        merged.update(incoming_workflow_ids)
        payload["workflow_ids"] = merged
    cfg.update_settings(**payload)
    return {"ok": True}
