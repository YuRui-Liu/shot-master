from drama_shot_master.core.result_parser import parse_result, ParsedResult


RAW = """这是 AI 输出的开场说明。

## 1. global_prompt
```
夕阳下她转身奔跑，长发被风扬起，眼神坚定。
```

## 2. timeline_data
```json
{
  "segments": [
    { "prompt": "画面描述：黄昏沙地，少女转身。", "length": 96, "color": "#4f8edc" },
    { "prompt": "画面发展：风扬起长发。", "length": 96, "color": "#e07b3a" }
  ]
}
```

## 3. local_prompts
```
画面描述：黄昏沙地，少女转身。 | 画面发展：风扬起长发。
```

## 4. segment_lengths
```
96, 96
```

## 5. max_frames
```
192
```

## 6. frame_indices
```
frame_idx_1 = 0
frame_idx_2 = 96
frame_idx_3 = -1
frame_idx_4 = -1
frame_idx_5 = -1
```

## 7. strengths
```
strength_1 = 1.0
strength_2 = 1.0
strength_3 = 0.0
strength_4 = 0.0
strength_5 = 0.0
```

## 8. epsilon
```
0.1
```

## 9. notes
- frame_idx_1 黄昏沙地少女转身
- frame_idx_2 风扬起长发
"""


def test_parse_basic_fields():
    r = parse_result(RAW)
    assert isinstance(r, ParsedResult)
    assert "夕阳下她转身奔跑" in r.global_prompt
    assert "segments" in r.timeline_data
    assert "黄昏沙地" in r.local_prompts
    assert r.segment_lengths == [96, 96]
    assert r.max_frames == 192
    assert r.frame_indices == [0, 96, -1, -1, -1]
    assert r.strengths == [1.0, 1.0, 0.0, 0.0, 0.0]
    assert r.epsilon == 0.1
    assert "frame_idx_1" in r.notes
    assert r.raw == RAW


def test_parse_missing_fields_yields_none():
    r = parse_result("没有任何代码块的文本")
    assert r.global_prompt == ""
    assert r.timeline_data == ""
    assert r.segment_lengths == []
    assert r.max_frames is None
    assert r.frame_indices == []
    assert r.epsilon is None


def test_parse_handles_chinese_field_labels():
    raw = """
## global_prompt
```
hi
```
"""
    r = parse_result(raw)
    assert r.global_prompt == "hi"


def test_parse_frame_indices_robust_to_missing_lines():
    raw = """
## frame_indices
```
frame_idx_1 = 0
frame_idx_2 = 48
```
"""
    r = parse_result(raw)
    # 不足 5 个，补 -1
    assert r.frame_indices == [0, 48, -1, -1, -1]
