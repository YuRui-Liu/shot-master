"""media_agent 配乐情绪分析端点 — 无 Qt、无网络、零 ffmpeg。

POST /soundtrack/analyze_segment：对 [start,end] 抽帧 → 多帧 vision 情绪分析 →
{labels, valence, arousal, intensity, suggested_tags}。

vision provider 与抽帧均经模块级工厂注入假实现：
  - _frame_extractor：不触 ffmpeg，按 times 造同等数量假 png 路径（不实际落盘也可，
    因为假 provider 不读文件）。
  - _vision_provider_factory：假 provider.generate 返回固定 JSON 情绪。
"""
from pathlib import Path

import media_agent.routes.soundtrack as st_mod
from fastapi.testclient import TestClient

from media_agent.server import create_app

client = TestClient(create_app())


class _FakeVisionProvider:
    """假 vision provider：generate(images, system, user) 返回固定情绪 JSON。"""

    def __init__(self, raw):
        self._raw = raw
        self.calls = []

    def generate(self, images, system_prompt, user_supplement):
        self.calls.append((list(images), system_prompt, user_supplement))
        return self._raw


def _patch(monkeypatch, *, raw, captured=None):
    """注入假抽帧 + 假 vision provider。captured(dict) 可用于回收调用参数。"""

    def fake_extract(video, times, out_dir):
        if captured is not None:
            captured["times"] = list(times)
            captured["video"] = video
        # 造与 times 一一对应的假 png 路径（不实际落盘，假 provider 不读）
        return [Path(out_dir) / f"f{i}.png" for i, _ in enumerate(times)]

    prov = _FakeVisionProvider(raw)
    if captured is not None:
        captured["provider"] = prov
    monkeypatch.setattr(st_mod, "_frame_extractor", fake_extract)
    monkeypatch.setattr(st_mod, "_vision_provider_factory", lambda cfg: prov)
    monkeypatch.setattr(st_mod, "_load_cfg", lambda: object())


# ---------- 正常路径：结构 + 字段范围 ----------

def test_analyze_segment_returns_structure(monkeypatch):
    raw = ('{"labels": ["tense", "ominous"], "valence": -0.6, '
           '"arousal": 0.85, "intensity": 0.7}')
    _patch(monkeypatch, raw=raw)
    r = client.post("/soundtrack/analyze_segment", json={
        "video": "/fake/clip.mp4", "start_sec": 2.0, "end_sec": 7.0,
        "hint": "cinematic suspense",
    })
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["labels"] == ["tense", "ominous"]
    assert 2 <= len(body["labels"]) <= 4
    assert -1.0 <= body["valence"] <= 1.0
    assert 0.0 <= body["arousal"] <= 1.0
    assert 0.0 <= body["intensity"] <= 1.0
    # suggested_tags 复用 prompt_composer：器乐 / dialogue-friendly / 含 hint 风格
    tags = body["suggested_tags"]
    assert isinstance(tags, str) and tags
    assert "Instrumental" in tags
    assert "dialogue-friendly" in tags
    assert "cinematic suspense" in tags
    assert "tense" in tags


def test_analyze_segment_extracts_three_frames(monkeypatch):
    cap = {}
    _patch(monkeypatch, raw='{"labels": ["calm"], "valence": 0.1, '
                            '"arousal": 0.2, "intensity": 0.4}', captured=cap)
    r = client.post("/soundtrack/analyze_segment", json={
        "video": "/fake/clip.mp4", "start_sec": 4.0, "end_sec": 10.0})
    assert r.status_code == 200, r.text
    # start / mid / end 三帧
    assert cap["times"] == [4.0, 7.0, 10.0]
    # provider 收到 3 张图
    images, _sys, _usr = cap["provider"].calls[0]
    assert len(images) == 3


def test_analyze_segment_no_hint_uses_default_style(monkeypatch):
    cap = {}
    _patch(monkeypatch, raw='{"labels": ["warm"], "valence": 0.5, '
                            '"arousal": 0.4, "intensity": 0.5}', captured=cap)
    r = client.post("/soundtrack/analyze_segment", json={
        "video": "/fake/clip.mp4", "start_sec": 0.0, "end_sec": 3.0})
    assert r.status_code == 200, r.text
    # 无 hint → 默认中性风格被喂进 vision user prompt 与 tags
    _imgs, _sys, usr = cap["provider"].calls[0]
    assert "neutral cinematic background" in usr
    assert "neutral cinematic background" in r.json()["suggested_tags"]


# ---------- 降级：解析失败 → 中性，不抛 ----------

def test_analyze_segment_parse_failure_neutral(monkeypatch):
    _patch(monkeypatch, raw="not a json at all")
    r = client.post("/soundtrack/analyze_segment", json={
        "video": "/fake/clip.mp4", "start_sec": 1.0, "end_sec": 5.0})
    assert r.status_code == 200, r.text
    body = r.json()
    # emotion_tagger 解析失败降级 _NEUTRAL：labels 空、arousal 0.3、intensity 0.5
    assert body["labels"] == []
    assert body["arousal"] == 0.3
    assert body["intensity"] == 0.5
    # 仍能组出 tags（mood 退化为 neutral, restrained）
    assert "Instrumental" in body["suggested_tags"]


# ---------- 边界校验：400 ----------

def test_analyze_segment_end_le_start_400(monkeypatch):
    _patch(monkeypatch, raw='{"labels": ["x"]}')
    r = client.post("/soundtrack/analyze_segment", json={
        "video": "/fake/clip.mp4", "start_sec": 5.0, "end_sec": 5.0})
    assert r.status_code == 400


def test_analyze_segment_negative_start_400(monkeypatch):
    _patch(monkeypatch, raw='{"labels": ["x"]}')
    r = client.post("/soundtrack/analyze_segment", json={
        "video": "/fake/clip.mp4", "start_sec": -1.0, "end_sec": 4.0})
    assert r.status_code == 400
