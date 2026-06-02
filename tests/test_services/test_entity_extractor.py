"""资源库抽取后端 extract_entities 单测（纯文本进出、可注入 provider、绝不连网络）。

覆盖（T2 · 资源库抽取后端）：
- mock provider 返回合法 JSON → 结果含 characters/scenes/props 三类名单。
- mock provider 返回非法 JSON → 三类皆空（降级不崩）。
- provider 抛异常 → 三类皆空（降级不崩）。
- provider 未配置（build 返回 None / 抛）→ 三类皆空。
- 空剧本文本 → 不调 provider，三类皆空。
"""
from __future__ import annotations

import json

from drama_shot_master.services.entity_extractor import extract_entities


# ---- 假 provider（记录入参 + 返回预设文本，绝不真连网络）-----------------

class _FakeProvider:
    """模拟 LLM provider：generate(images, system_prompt, user_supplement) -> str。

    raw 为预设返回文本；raise_exc=True 时调用即抛，模拟网络/解析前异常。
    """

    def __init__(self, raw: str = "", *, raise_exc: bool = False):
        self.raw = raw
        self.raise_exc = raise_exc
        self.calls: list[dict] = []

    def generate(self, images, system_prompt, user_supplement) -> str:
        self.calls.append({
            "images": list(images),
            "system_prompt": system_prompt,
            "user_supplement": user_supplement,
        })
        if self.raise_exc:
            raise RuntimeError("provider boom")
        return self.raw


_SCRIPT = "女主在古城墙下握着宝剑，男主骑马而来。场景：黄昏的古城。"


# ---- 合法 JSON → 三类名单 -------------------------------------------------

def test_extract_returns_three_categories():
    payload = {
        "characters": ["女主", "男主"],
        "scenes": ["古城墙", "黄昏的古城"],
        "props": ["宝剑", "马"],
    }
    provider = _FakeProvider(json.dumps(payload, ensure_ascii=False))

    result = extract_entities(_SCRIPT, cfg=object(), provider=provider)

    assert set(result.keys()) == {"characters", "scenes", "props"}
    assert result["characters"] == ["女主", "男主"]
    assert result["scenes"] == ["古城墙", "黄昏的古城"]
    assert result["props"] == ["宝剑", "马"]


def test_extract_tolerates_json_in_code_fence():
    """LLM 常用 ```json 包裹 → 仍能解析出三类。"""
    payload = {"characters": ["A"], "scenes": ["B"], "props": ["C"]}
    raw = "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
    provider = _FakeProvider(raw)

    result = extract_entities(_SCRIPT, cfg=object(), provider=provider)

    assert result["characters"] == ["A"]
    assert result["scenes"] == ["B"]
    assert result["props"] == ["C"]


def test_extract_passes_script_text_to_provider():
    """剧本文本进 user_supplement，纯文本进出（images 为空）。"""
    provider = _FakeProvider('{"characters":[],"scenes":[],"props":[]}')

    extract_entities(_SCRIPT, cfg=object(), provider=provider)

    assert len(provider.calls) == 1
    call = provider.calls[0]
    assert call["images"] == []
    assert _SCRIPT in call["user_supplement"]


# ---- 降级：非法 JSON / provider 抛 / 未配置 → 空三类 -----------------------

def _assert_empty(result: dict):
    assert result == {"characters": [], "scenes": [], "props": []}


def test_extract_invalid_json_returns_empty():
    provider = _FakeProvider("这不是 JSON，随便一段话")
    _assert_empty(extract_entities(_SCRIPT, cfg=object(), provider=provider))


def test_extract_provider_raises_returns_empty():
    provider = _FakeProvider(raise_exc=True)
    _assert_empty(extract_entities(_SCRIPT, cfg=object(), provider=provider))


def test_extract_no_provider_configured_returns_empty():
    """provider=None 且 build 失败/未配置 → 空三类（降级不崩）。"""
    def _build_none(cfg):
        return None

    _assert_empty(extract_entities(
        _SCRIPT, cfg=object(), provider_builder=_build_none))


def test_extract_builder_raises_returns_empty():
    def _build_boom(cfg):
        raise RuntimeError("no creds")

    _assert_empty(extract_entities(
        _SCRIPT, cfg=object(), provider_builder=_build_boom))


def test_extract_empty_script_returns_empty_without_calling_provider():
    provider = _FakeProvider('{"characters":["X"],"scenes":[],"props":[]}')
    result = extract_entities("   ", cfg=object(), provider=provider)
    _assert_empty(result)
    assert provider.calls == []


# ---- JSON 字段缺失 / 类型杂质 → 安全归一 ----------------------------------

def test_extract_missing_keys_filled_with_empty_lists():
    provider = _FakeProvider('{"characters":["仅角色"]}')
    result = extract_entities(_SCRIPT, cfg=object(), provider=provider)
    assert result["characters"] == ["仅角色"]
    assert result["scenes"] == []
    assert result["props"] == []


def test_extract_filters_non_string_and_blank_items():
    raw = json.dumps({
        "characters": ["女主", "", "  ", 123, None, "女主"],
        "scenes": ["古城"],
        "props": [],
    }, ensure_ascii=False)
    provider = _FakeProvider(raw)
    result = extract_entities(_SCRIPT, cfg=object(), provider=provider)
    # 去空白、去非字符串、去重，保序
    assert result["characters"] == ["女主"]
    assert result["scenes"] == ["古城"]
    assert result["props"] == []
