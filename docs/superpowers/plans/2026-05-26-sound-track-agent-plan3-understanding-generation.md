# sound_track_agent Plan 3：理解 + 生成（情绪/prompt/ACE-Step）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 把"段落帧 → 情绪 → ACE-Step 三元组 prompt → RunningHub 生成 BGM"这条理解+生成链路落地。

**Architecture:** 4 个 task。(1) 修 `provider.py` 让它复用 refine 配置（实测有效 doubao key 在 `refine_api_key`）。(2) `emotion_tagger` 用豆包 vision 把代表帧判成 `EmotionTag`。(3) `prompt_composer` 增加 `compose_acestep_inputs` 输出 `(tags, bpm, duration)` 三元组。(4) `music_generator` 复用 runninghub client 把三元组注入 ACE-Step workflow（WorkflowID `2059090557116440578`）生成候选 BGM。

**Tech Stack:** openai SDK（已装 /usr/bin/python3）、豆包 `doubao-seed-2-0-lite-260215`（已验证支持 vision）、RunningHub ACE-Step。复用 Plan 1 的 `EmotionTag`/`BGMCandidate`、`drama_shot_master.providers.runninghub.RunningHubClient`、`core.prompt_refiner`。

参考 spec：`docs/superpowers/specs/2026-05-25-sound-track-agent-design.md`。测试用 `/usr/bin/python3 -m pytest`。

## 已验证事实（实测）

- `doubao-seed-2-0-lite-260215` 支持图像，返回准确情绪 JSON。
- **有效 key 在 `cfg.refine_api_key`（settings.json），`.env DOUBAO_API_KEY` 为空**。
- `VisionProvider.generate(images: list[Path], system_prompt: str, user_supplement: str) -> str`。
- ACE-Step 注入字段：node94 `tags`、node203 `value`(bpm int)、node205 `value`(duration float)、node109 `value`(seed int)。
- RunningHubClient：`create_task(workflow_id=, node_info_list=) -> task_id`；`query_task(task_id) -> {status, results:[{url,outputType}], errorMessage}`；`download_file(url, dest) -> dest`。status ∈ QUEUED/RUNNING/SUCCESS/FAILED。

---

## Task 1：provider.py 复用 refine 配置

**Files:**
- Modify: `sound_track_agent/provider.py`
- Test: `tests/test_sound_track_agent/test_provider.py`（追加 2 个测试）

- [ ] **Step 1: 追加失败测试**

在 `tests/test_sound_track_agent/test_provider.py` 末尾追加：

```python
def test_falls_back_to_refine_when_no_soundtrack_or_doubao():
    cfg = _Cfg(refine_api_key="k-refine",
               refine_base_url="https://ark.example/api/v3",
               refine_model="doubao-seed-2-0-lite-260215")
    p = build_soundtrack_provider(cfg)
    assert p.config.api_key == "k-refine"
    assert p.config.base_url == "https://ark.example/api/v3"
    assert p.config.model == "doubao-seed-2-0-lite-260215"


def test_refine_takes_priority_over_doubao_envkeys():
    cfg = _Cfg(api_keys={"doubao": "k-doubao"},
               base_urls={"doubao": "https://doubao.example/v3"},
               refine_api_key="k-refine",
               refine_base_url="https://refine.example/v3")
    p = build_soundtrack_provider(cfg)
    assert p.config.api_key == "k-refine"           # refine 优先于 .env doubao
    assert p.config.base_url == "https://refine.example/v3"
```

- [ ] **Step 2: 跑确认失败**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_provider.py -q`
Expected: 2 新测试 FAIL（当前用 doubao，refine key 被忽略）。

- [ ] **Step 3: 改 build_soundtrack_provider 取值优先级**

把 `sound_track_agent/provider.py` 的 `build_soundtrack_provider` 三处取值改为加入 refine 回退（顺序：`soundtrack_*` → `refine_*` → `api_keys/base_urls['doubao']` → 默认）：

```python
def build_soundtrack_provider(cfg):
    """用配乐专属/refine/豆包配置构造 vision provider。

    取值优先级：cfg.soundtrack_* → cfg.refine_*（提示词优化同款）
    → cfg.api_keys/base_urls['doubao'] → 默认。
    实测有效豆包 key 在 refine_api_key，故 refine 回退必不可少。
    """
    from drama_shot_master.providers.openai_compat import OpenAICompatProvider
    from drama_shot_master.providers.base import ProviderConfig

    api_key = (getattr(cfg, "soundtrack_api_key", "")
               or getattr(cfg, "refine_api_key", "")
               or getattr(cfg, "api_keys", {}).get("doubao", ""))
    base_url = (getattr(cfg, "soundtrack_base_url", "")
                or getattr(cfg, "refine_base_url", "")
                or getattr(cfg, "base_urls", {}).get("doubao", "")
                or DEFAULT_BASE_URL)
    model = (getattr(cfg, "soundtrack_model", "")
             or getattr(cfg, "refine_model", "")
             or DEFAULT_MODEL)

    return OpenAICompatProvider(ProviderConfig(
        api_key=api_key or "x",
        base_url=base_url,
        model=model,
        timeout=REQUEST_TIMEOUT,
    ))
```

- [ ] **Step 4: 跑确认通过**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_provider.py -q`
Expected: **5 passed**（原 3 + 新 2）。原有测试仍过：无 refine 属性时 `getattr` 返回 ""，回退到 doubao。

- [ ] **Step 5: Commit**

```bash
git add sound_track_agent/provider.py tests/test_sound_track_agent/test_provider.py
git commit -m "fix(sound_track_agent): provider 复用 refine 配置（有效豆包 key 在 refine_api_key）"
```

---

## Task 2：emotion_tagger（豆包 vision → EmotionTag）

**Files:**
- Create: `sound_track_agent/emotion_tagger.py`
- Test: `tests/test_sound_track_agent/test_emotion_tagger.py`

**逻辑**：`tag_emotion(provider, frame_path, global_style) -> EmotionTag`。组 system/user prompt，调 `provider.generate([frame], sys, usr)`，解析返回 JSON（labels/valence/arousal）→ EmotionTag。解析失败 → 降级返回中性 EmotionTag（不抛，保证 pipeline 不中断）。解析逻辑（去 code fence + json.loads）抽成可单测的 `_parse_emotion`。

- [ ] **Step 1: 写失败测试**

`tests/test_sound_track_agent/test_emotion_tagger.py`:

```python
from pathlib import Path
from sound_track_agent.emotion_tagger import tag_emotion, _parse_emotion
from sound_track_agent.session import EmotionTag


class _FakeProvider:
    def __init__(self, reply): self._reply = reply; self.calls = []
    def generate(self, images, system_prompt, user_supplement):
        self.calls.append((list(images), system_prompt, user_supplement))
        return self._reply


def test_parse_emotion_plain_json():
    raw = '{"labels":["tense","eerie"],"valence":-0.7,"arousal":0.8}'
    e = _parse_emotion(raw)
    assert e.labels == ["tense", "eerie"]
    assert e.valence == -0.7
    assert e.arousal == 0.8


def test_parse_emotion_strips_code_fence():
    raw = '```json\n{"labels":["calm"],"valence":0.3,"arousal":0.2}\n```'
    e = _parse_emotion(raw)
    assert e.labels == ["calm"]
    assert e.arousal == 0.2


def test_parse_emotion_bad_json_returns_neutral():
    e = _parse_emotion("sorry I cannot")
    assert e.labels == []          # 降级中性
    assert e.valence == 0.0
    assert e.arousal == 0.3


def test_tag_emotion_calls_provider_and_parses(tmp_path):
    img = tmp_path / "f.png"; img.write_bytes(b"x")
    prov = _FakeProvider('{"labels":["sad"],"valence":-0.5,"arousal":0.3}')
    e = tag_emotion(prov, img, global_style="末日废土")
    assert isinstance(e, EmotionTag)
    assert e.labels == ["sad"]
    # 传了图 + global_style 进 prompt
    images, sys_p, usr = prov.calls[0]
    assert images == [img]
    assert "末日废土" in (sys_p + usr)
```

- [ ] **Step 2: 跑确认失败**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_emotion_tagger.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 emotion_tagger.py**

```python
"""段落代表帧 → 情绪标签（豆包 vision）。解析失败降级中性，不中断管线。"""
from __future__ import annotations

import json
from pathlib import Path

from sound_track_agent.session import EmotionTag

_NEUTRAL = EmotionTag(labels=[], valence=0.0, arousal=0.3, intensity=0.5)


def _strip_code_fence(text: str) -> str:
    t = text.strip()
    if not t.startswith("```"):
        return t
    lines = t.split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_emotion(raw: str) -> EmotionTag:
    """解析模型 JSON → EmotionTag；任何异常降级为中性。"""
    try:
        obj = json.loads(_strip_code_fence(raw))
        if not isinstance(obj, dict):
            return _NEUTRAL
        labels = obj.get("labels") or []
        if not isinstance(labels, list):
            labels = []
        return EmotionTag(
            labels=[str(x) for x in labels],
            valence=float(obj.get("valence", 0.0)),
            arousal=float(obj.get("arousal", 0.3)),
            intensity=float(obj.get("intensity", 0.5)),
        )
    except (ValueError, TypeError):
        return _NEUTRAL


_SYS = ("你是视频配乐的情绪分析助手。仔细观察画面，结合作品总体风格，"
        "判断这一段落的情绪基调与氛围。")
_USR_TMPL = ('作品总体风格：{style}\n'
             '用 JSON 输出该画面情绪（只输出 JSON）：'
             '{{"labels":[2-4个英文情绪标签], "valence":-1到1小数, '
             '"arousal":0到1小数, "intensity":0到1小数}}')


def tag_emotion(provider, frame_path: Path, global_style: str) -> EmotionTag:
    """用 vision provider 把代表帧判成 EmotionTag。"""
    raw = provider.generate([Path(frame_path)], _SYS,
                            _USR_TMPL.format(style=global_style))
    return _parse_emotion(raw)
```

- [ ] **Step 4: 跑确认通过**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_emotion_tagger.py -q`
Expected: **4 passed**

- [ ] **Step 5: Commit**

```bash
git add sound_track_agent/emotion_tagger.py tests/test_sound_track_agent/test_emotion_tagger.py
git commit -m "feat(sound_track_agent): emotion_tagger 豆包 vision 判情绪"
```

---

## Task 3：prompt_composer 增加 ACE-Step 三元组

**Files:**
- Modify: `sound_track_agent/prompt_composer.py`（新增 `compose_acestep_inputs`，保留旧 `compose_music_prompt`）
- Test: `tests/test_sound_track_agent/test_prompt_composer.py`（追加）

**逻辑**：`compose_acestep_inputs(global_style, emotion, duration) -> (tags, bpm, duration)`。tags = `"Instrumental, no vocals, " + global_style + 情绪标签 + "[Intro][main theme][fade out]"`（逗号分隔，贴合 ACE-Step tags 风格）。bpm 由 arousal 映射成整数（复用 `_tempo_hint` 的分档，取区间中值）。duration 原样返回（float）。

- [ ] **Step 1: 追加失败测试**

在 `tests/test_sound_track_agent/test_prompt_composer.py` 末尾追加：

```python
from sound_track_agent.prompt_composer import compose_acestep_inputs


def test_acestep_inputs_returns_triple():
    emo = EmotionTag(labels=["tense", "eerie"], arousal=0.8)
    tags, bpm, dur = compose_acestep_inputs("末日废土冷色调", emo, 12.5)
    assert isinstance(tags, str) and isinstance(bpm, int) and isinstance(dur, float)
    assert "Instrumental" in tags and "no vocals" in tags
    assert "末日废土冷色调" in tags
    assert "tense" in tags and "eerie" in tags
    assert dur == 12.5
    assert 110 <= bpm <= 140        # 高 arousal → 快 BPM


def test_acestep_inputs_low_arousal_slow_bpm():
    _, bpm, _ = compose_acestep_inputs("古风", EmotionTag(labels=["calm"], arousal=0.1), 8.0)
    assert 60 <= bpm <= 80


def test_acestep_inputs_no_emotion_neutral():
    tags, bpm, dur = compose_acestep_inputs("treasure", None, 5.0)
    assert "treasure" in tags
    assert isinstance(bpm, int)
    assert dur == 5.0
```

- [ ] **Step 2: 跑确认失败**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_prompt_composer.py -q`
Expected: 3 新测试 FAIL（ImportError）

- [ ] **Step 3: 追加 compose_acestep_inputs**

在 `sound_track_agent/prompt_composer.py` 末尾追加：

```python
def _bpm_from_arousal(arousal: float) -> int:
    """arousal → BPM 整数（取 _tempo_hint 分档的区间中值）。"""
    if arousal >= 0.66:
        return 125          # 110-140 中值
    if arousal >= 0.33:
        return 98           # 85-110 中值
    return 70               # 60-80 中值


def compose_acestep_inputs(global_style: str,
                           emotion: Optional[EmotionTag],
                           duration: float) -> tuple[str, int, float]:
    """生成 ACE-Step 三元组：(tags, bpm, duration)。

    tags 为逗号分隔的纯器乐风格/情绪标签 + 结构标记（贴合 TextEncodeAceStepAudio1.5）。
    bpm/duration 走 ACE-Step 的独立数值节点，不塞进 tags 文字。
    """
    labels = emotion.labels if emotion else []
    arousal = emotion.arousal if emotion else 0.3
    mood = ", ".join(labels) if labels else "neutral, restrained"
    tags = (f"Instrumental, no vocals, pure instrumental BGM, "
            f"{global_style}, {mood}, soft dynamics, dialogue-friendly, "
            f"[Intro soft opening], [Short main theme], [Quick smooth fade out]")
    return tags, _bpm_from_arousal(arousal), float(duration)
```

- [ ] **Step 4: 跑确认通过**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_prompt_composer.py -q`
Expected: **6 passed**（原 3 + 新 3）

- [ ] **Step 5: Commit**

```bash
git add sound_track_agent/prompt_composer.py tests/test_sound_track_agent/test_prompt_composer.py
git commit -m "feat(sound_track_agent): prompt_composer ACE-Step 三元组(tags,bpm,duration)"
```

---

## Task 4：music_generator（RunningHub ACE-Step）

**Files:**
- Create: `sound_track_agent/music_generator.py`
- Test: `tests/test_sound_track_agent/test_music_generator.py`

**逻辑**：`generate_bgm(client, workflow_id, tags, bpm, duration, out_dir, *, seeds) -> list[BGMCandidate]`。对每个 seed：用 `client.create_task(workflow_id=..., node_info_list=[...])` 注入 node94 tags / node203 bpm / node205 duration / node109 seed → `_wait_success(client, task_id)` 轮询到 SUCCESS 取 `results[0]["url"]` → `client.download_file(url, dest)` → `BGMCandidate(path, seed, prompt=tags)`。`_wait_success` 抽出便于注入/测试（接受可选 sleep/poll 注入）。

- [ ] **Step 1: 写失败测试**

`tests/test_sound_track_agent/test_music_generator.py`:

```python
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from sound_track_agent.music_generator import generate_bgm, NODE_TAGS, NODE_BPM, NODE_DUR, NODE_SEED
from sound_track_agent.session import BGMCandidate


def _client(success_url="https://x/bgm.mp3"):
    c = MagicMock()
    c.create_task.return_value = "tid-1"
    c.query_task.return_value = {"status": "SUCCESS",
                                 "results": [{"url": success_url, "outputType": "mp3"}]}
    c.download_file.side_effect = lambda url, dest: Path(dest)
    return c


def test_generate_bgm_injects_correct_node_info(tmp_path):
    c = _client()
    out = generate_bgm(c, "wf-9", tags="Instrumental, calm",
                       bpm=98, duration=12.5, out_dir=tmp_path,
                       seeds=[7])
    assert len(out) == 1
    assert isinstance(out[0], BGMCandidate)
    assert out[0].seed == 7
    # 校验注入的 nodeInfoList
    call = c.create_task.call_args
    assert call.kwargs["workflow_id"] == "wf-9"
    nil = {(it["nodeId"], it["fieldName"]): it["fieldValue"]
           for it in call.kwargs["node_info_list"]}
    assert nil[(NODE_TAGS, "tags")] == "Instrumental, calm"
    assert nil[(NODE_BPM, "value")] == 98
    assert nil[(NODE_DUR, "value")] == 12.5
    assert nil[(NODE_SEED, "value")] == 7


def test_generate_bgm_multiple_candidates_distinct_seeds(tmp_path):
    c = _client()
    out = generate_bgm(c, "wf-9", tags="t", bpm=90, duration=5.0,
                       out_dir=tmp_path, seeds=[1, 2, 3])
    assert [b.seed for b in out] == [1, 2, 3]
    assert c.create_task.call_count == 3


def test_generate_bgm_raises_on_failed_status(tmp_path):
    c = _client()
    c.query_task.return_value = {"status": "FAILED",
                                 "errorMessage": "oom", "results": None}
    with pytest.raises(RuntimeError, match="FAILED"):
        generate_bgm(c, "wf-9", tags="t", bpm=90, duration=5.0,
                     out_dir=tmp_path, seeds=[1])
```

- [ ] **Step 2: 跑确认失败**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_music_generator.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 music_generator.py**

```python
"""RunningHub ACE-Step 文生音乐：注入 (tags,bpm,duration,seed) → 候选 BGM。

复用 drama_shot_master.providers.runninghub.RunningHubClient（create_task/query_task/
download_file）。WorkflowID 由调用方传入（默认见 spec：2059090557116440578）。
"""
from __future__ import annotations

import time
from pathlib import Path

from sound_track_agent.session import BGMCandidate

# ACE-Step workflow 节点 id（见 spec §11）
NODE_TAGS = "94"     # TextEncodeAceStepAudio1.5.tags
NODE_BPM = "203"     # Int.value（每分钟节拍数）
NODE_DUR = "205"     # Float.value（歌曲时长秒）
NODE_SEED = "109"    # PrimitiveInt.value（随机种子）

_TERMINAL_OK = "SUCCESS"
_TERMINAL_FAIL = "FAILED"


def _node_info(tags: str, bpm: int, duration: float, seed: int) -> list[dict]:
    return [
        {"nodeId": NODE_TAGS, "fieldName": "tags", "fieldValue": tags},
        {"nodeId": NODE_BPM, "fieldName": "value", "fieldValue": int(bpm)},
        {"nodeId": NODE_DUR, "fieldName": "value", "fieldValue": float(duration)},
        {"nodeId": NODE_SEED, "fieldName": "value", "fieldValue": int(seed)},
    ]


def _wait_success(client, task_id: str, *,
                  timeout: float = 600.0, poll_interval: float = 5.0,
                  sleep=time.sleep) -> str:
    """轮询到 SUCCESS，返回首个结果 url。FAILED/超时抛 RuntimeError。"""
    waited = 0.0
    while True:
        d = client.query_task(task_id)
        status = d.get("status")
        if status == _TERMINAL_OK:
            results = d.get("results") or []
            if not results:
                raise RuntimeError(f"task {task_id} SUCCESS 但无 results")
            return results[0]["url"]
        if status == _TERMINAL_FAIL:
            raise RuntimeError(
                f"task {task_id} FAILED: {d.get('errorMessage', '')}")
        if waited >= timeout:
            raise RuntimeError(f"task {task_id} 轮询超时（{timeout}s）")
        sleep(poll_interval)
        waited += poll_interval


def generate_bgm(client, workflow_id: str, *,
                 tags: str, bpm: int, duration: float,
                 out_dir: Path, seeds: list[int],
                 timeout: float = 600.0, poll_interval: float = 5.0,
                 sleep=time.sleep) -> list[BGMCandidate]:
    """对每个 seed 生成一个候选 BGM。返回 BGMCandidate 列表。"""
    out_dir = Path(out_dir)
    candidates: list[BGMCandidate] = []
    for seed in seeds:
        task_id = client.create_task(
            workflow_id=workflow_id,
            node_info_list=_node_info(tags, bpm, duration, seed))
        url = _wait_success(client, task_id, timeout=timeout,
                            poll_interval=poll_interval, sleep=sleep)
        dest = out_dir / f"bgm_seed{seed}.mp3"
        client.download_file(url, dest)
        candidates.append(BGMCandidate(path=str(dest), seed=seed, prompt=tags))
    return candidates
```

- [ ] **Step 4: 跑确认通过 + 全量回归**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_music_generator.py -q`
Expected: **3 passed**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/ -q`
Expected: 全量通过（Plan1 27 + Plan2 8 + Plan3：provider 新增 2 + emotion 4 + prompt 新增 3 + music 3 = 47）

- [ ] **Step 5: Commit**

```bash
git add sound_track_agent/music_generator.py tests/test_sound_track_agent/test_music_generator.py
git commit -m "feat(sound_track_agent): music_generator RunningHub ACE-Step 生成候选 BGM"
```

---

## 后续 Plan 预告

- **Plan 4 对齐+混音**：`beat_aligner` 接 `librosa.beat.beat_track`（需装 librosa）取真实 beat + pyrubberband time-stretch；`audio_mixer`（Demucs 分离对白 + FFmpeg sidechain ducking + loudnorm）。
- **集成**：把 `pipeline.Stages` 的 stub 换成真实实现——`tag_emotion`=emotion_tagger、`compose_prompt`/`generate` 用 prompt_composer 三元组 + music_generator（SegmentScore 需能存 (tags,bpm,duration) 或在 generate 阶段现算）、`align`/`mix`=Plan 4。CLI `run` 接线 detect_shots→plan_segments→…。
- **接线注意**：pipeline 现有 `compose_prompt: (seg,sess)->str` 与新三元组不完全匹配，集成时要决定把 bpm/duration 存哪（建议 SegmentScore 加 music_prompt 存 tags、另在 generate 阶段用 emotion+duration 现算 bpm/duration，避免改 session schema）。
