"""LTX nodeInfoList 与「真实工作流 JSON」契约对齐回归测试。

source of truth = 用户真机实际部署在 RunningHub 上的工作流导出：
  comfyui_workflow/LTX2.3 导演台_api.json        (profile director,    node 4/32/23/34)
  comfyui_workflow/LTX2.3 高清导演台_api.json     (profile director_v3, node 672/683/654/687)

排查 code=805（工作流执行失败）的根因假设是：builder 覆盖的 nodeId/字段
与真实工作流不匹配 → 服务端按未知节点/字段执行失败。本测试把这个不变量
钉死：**build_node_info_list 产出的每个 (nodeId, fieldName) 都必须在对应
真实工作流 JSON 里真实存在**（节点存在 + 该节点 inputs 里有这个字段）。

同时回归 16:9：
  - director  经 node 34 TTResolutionSelector，custom_width > custom_height；
  - director_v3 无 ResolutionSelector → 落 node 672 LTXDirector 的 custom_width/height，
    同样 custom_width > custom_height。

⚠ 关于「16:9 变正方形」的存疑点（在代码注释而非断言里标注）：
  两个真实工作流的 LTXDirector 节点 resize_method 均为 "maintain aspect ratio"，
  divisible_by=32。该模式下 custom_width/height 实为**外接框**，模型按**输入首帧图
  的宽高比**去贴合这个框——若传入首帧图本身是正方形，输出就会是正方形，与传入的
  1280x720 无关。故 nodeInfoList 把 custom_width/height 设成 16:9 是必要但**不充分**
  条件；真正保证 16:9 还需保证首帧图本身是 16:9（这部分在上游出图/裁切处保证，
  不在 builder 职责内）。本测试只校验 builder 侧把宽高设成了 16:9。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from drama_shot_master.core import workflow_profiles as wp
from drama_shot_master.providers.runninghub import (
    LTXDirectorSpec, LTXSegment, LTXTaskBuilder,
)

_ROOT = Path(__file__).resolve().parent.parent.parent
_CW = _ROOT / "comfyui_workflow"

# profile key → 真实工作流导出 JSON（source of truth）
_REAL_WORKFLOW = {
    "director": _CW / "LTX2.3 导演台_api.json",
    "director_v3": _CW / "LTX2.3 高清导演台_api.json",
}


def _load_real(profile_key: str) -> dict:
    p = _REAL_WORKFLOW[profile_key]
    assert p.exists(), f"真实工作流缺失: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


def _build_items(profile_key: str, **spec_overrides) -> list[dict]:
    prof = wp.PROFILES[profile_key]
    builder = LTXTaskBuilder(wp.template_path_for(prof), prof)
    img = Path("/frame.png")
    base = dict(
        global_prompt="g",
        segments=(
            LTXSegment(local_prompt="s1", length=33, image_path=img),
            LTXSegment(local_prompt="s2", length=33, image_path=img),
        ),
        noise_seed=12345,          # 强制带上 noise_node 覆盖项
        use_custom_audio=True,     # 强制带上 audio_switch_node 覆盖项（v3）
    )
    base.update(spec_overrides)
    spec = LTXDirectorSpec(**base)
    return builder.build_node_info_list(spec, {img: "openapi/frame.png"})


# ---------- 核心：覆盖的 nodeId / field 必须存在于真实工作流 ----------

@pytest.mark.parametrize("profile_key", ["director", "director_v3"])
def test_every_overridden_node_exists_in_real_workflow(profile_key):
    real = _load_real(profile_key)
    items = _build_items(profile_key)
    missing_nodes = sorted({it["nodeId"] for it in items
                            if it["nodeId"] not in real})
    assert not missing_nodes, (
        f"[{profile_key}] nodeInfoList 覆盖了真实工作流不存在的节点: "
        f"{missing_nodes}（真机会按 code=805 执行失败）")


@pytest.mark.parametrize("profile_key", ["director", "director_v3"])
def test_every_overridden_field_exists_on_real_node(profile_key):
    real = _load_real(profile_key)
    items = _build_items(profile_key)
    bad: list[str] = []
    for it in items:
        nid, field = it["nodeId"], it["fieldName"]
        node = real.get(nid)
        if node is None:
            continue  # 节点缺失由上一个测试报
        if field not in node.get("inputs", {}):
            bad.append(
                f"node {nid} ({node.get('class_type')}) 无字段 {field}")
    assert not bad, (
        f"[{profile_key}] nodeInfoList 覆盖了真实节点上不存在的字段: {bad}")


@pytest.mark.parametrize("profile_key,expected_nodes", [
    ("director", {"4", "32", "34"}),       # director_node / save_video / resolution
    ("director_v3", {"672", "683", "687"}),  # director_node / save_video / audio_switch
])
def test_expected_real_node_ids_are_covered(profile_key, expected_nodes):
    """正向确认：profile 映射的关键真实节点 ID 确实被 builder 覆盖到。"""
    items = _build_items(profile_key)
    covered = {it["nodeId"] for it in items}
    assert expected_nodes.issubset(covered), (
        f"[{profile_key}] 期望覆盖 {expected_nodes}，实际 {sorted(covered)}")


# ---------- noise_seed 落在真实 RandomNoise 节点 ----------

@pytest.mark.parametrize("profile_key,noise_node", [
    ("director", "23"),
    ("director_v3", "654"),
])
def test_noise_seed_lands_on_real_random_noise_node(profile_key, noise_node):
    real = _load_real(profile_key)
    assert real[noise_node]["class_type"] == "RandomNoise"
    items = _build_items(profile_key)
    seed = [it for it in items
            if it["nodeId"] == noise_node and it["fieldName"] == "noise_seed"]
    assert seed and seed[0]["fieldValue"] == 12345


# ---------- 16:9 回归 ----------

def test_director_16_9_resolution_landscape():
    """director：经 node 34 TTResolutionSelector，custom_width > custom_height。

    node 4 LTXDirector.custom_width/height 在真实工作流里连到 [34,0]/[34,1]，
    故覆盖 node 34 即生效。默认预设 "1280x720 (16:9) (横屏)" → 1280>720。
    """
    real = _load_real("director")
    assert real["34"]["class_type"] == "TTResolutionSelector"
    # node 4 的 custom_width/height 确实连到 node 34（而非字面量）
    assert real["4"]["inputs"]["custom_width"] == ["34", 0]
    assert real["4"]["inputs"]["custom_height"] == ["34", 1]

    items = _build_items("director")  # 默认 resolution_preset 即 16:9 横屏
    res = {it["fieldName"]: it["fieldValue"]
           for it in items if it["nodeId"] == "34"}
    assert res.get("use_custom_resolution") is True
    assert res["custom_width"] > res["custom_height"], res
    assert (res["custom_width"], res["custom_height"]) == (1280, 720)


def test_director_v3_16_9_lands_on_director_custom_wh():
    """director_v3：无 ResolutionSelector → 落 node 672 LTXDirector 字面 custom_width/height。

    真实工作流 node 672 的 custom_width/height 是字面整数（非连线），故 builder
    直接覆盖它即可；16:9 横屏预设 → custom_width > custom_height。
    """
    real = _load_real("director_v3")
    assert real["672"]["class_type"] == "LTXDirector"
    # 真实工作流里 672 的 custom_width/height 是字面量（int），不是连线（list）
    assert isinstance(real["672"]["inputs"]["custom_width"], int)
    assert isinstance(real["672"]["inputs"]["custom_height"], int)
    # 且没有 TTResolutionSelector 节点
    assert not any(n.get("class_type") == "TTResolutionSelector"
                   for n in real.values())

    items = _build_items("director_v3",
                         resolution_preset="1280x720 (16:9) (横屏)")
    w = [it for it in items
         if it["nodeId"] == "672" and it["fieldName"] == "custom_width"]
    h = [it for it in items
         if it["nodeId"] == "672" and it["fieldName"] == "custom_height"]
    assert w and h
    assert w[0]["fieldValue"] == 1280
    assert h[0]["fieldValue"] == 720
    assert w[0]["fieldValue"] > h[0]["fieldValue"]
