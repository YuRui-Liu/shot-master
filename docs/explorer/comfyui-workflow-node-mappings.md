# ComfyUI Workflow Node Mapping for RunningHub API

Generated 2026-06-01. Maps workflow JSON nodes to backend `nodeInfoList` parameters sent to RunningHub.

---

## 1. Qwen3 TTS Voice Design (`Qwen3 TTS 音色设计_api.json`)

| Backend Accessor | node_id | fieldName | Type | Default in Workflow | Notes |
|---|---|---|---|---|---|
| `prof.nodes["text"]` | **14** | `text` | string | `"土豆今天又加班了！需要亲亲抱抱举高高"` | Text node titled "生成内容"; utterance to speak |
| `prof.nodes["style"]` | **15** | `text` | string | `"体现慵懒魅惑的御姐女声..."` | Text node titled "audio style"; voice style/character description |
| `prof.nodes["voice_design"]` | **22** | `language` | string (enum) | `"Auto"` | TDQwen3TTSVoiceDesign node; language enum widget |
| `prof.nodes["voice_design"]` | **22** | `text` | string (input) | (from node 14) | Connected text input - overridden indirectly via text node |
| `prof.nodes["voice_design"]` | **22** | `instruct` | string (input) | (from node 15) | Connected instruct/style input - overridden indirectly via style node |
| `prof.nodes["voice_design"]` | **22** | `model` | input (from node 23) | model loader output | Not overridden |
| (model loader) | **23** | `model_path` | string | `"Qwen3-TTS-12Hz-1.7B-VoiceDesign"` | TDQwen3TTSModelLoader; not overridden by backend |
| (model loader) | **23** | `precision` | string | `"bf16"` | Not overridden |
| (model loader) | **23** | `device` | string | `"cuda"` | Not overridden |
| (save audio) | **18** | `filename_prefix` | string | `"audio/ComfyUI"` | SaveAudio (FLAC); not overridden |

### Backend code path
- `drama_shot_master/core/tts_profiles.py`: `VOICE_DESIGN` profile maps `text="14"`, `style="15"`, `voice_design="22"`
- `drama_shot_master/providers/tts_builder.py:build_design_node_info()` builds `nodeInfoList`

### Parameter mapping (backend sends)
```python
{"nodeId": "14", "fieldName": "text", "fieldValue": user_text}
{"nodeId": "15", "fieldName": "text", "fieldValue": style_description}
{"nodeId": "22", "fieldName": "language", "fieldValue": "Auto"|"zh"|"en"|...}
```

### Notable gaps / issues
- **No `speed` field exists** in the Qwen3 TTS Voice Design workflow (node 22 has `text`, `instruct`, `language`, `model`). The backend does not send a `speed` parameter. Despite the `_meta.title` suggesting this is a Qwen3 TTS Voice Design node, the `class_type` is `TDQwen3TTSVoiceDesign` which has no speed/speed widget defined in this workflow.

---

## 2. TTS2 Emotion Voice Clone (`TTS2 情感声音克隆_input_switch_api.json`)

### Key node architecture
The workflow uses a **PrimitiveInt → ImpactSwitch cascade** design. One selector integer (node 103) feeds into 4 ImpactSwitch nodes that route different inputs to the single `IndexTTS2Run` executor (node 1).

| Backend Accessor | node_id | fieldName | Type | Default | Notes |
|---|---|---|---|---|---|
| `prof.nodes["text"]` | **4** | `prompt` | string | `"第二年春，它又开了。"` | CR Prompt Text; the text to speak |
| `prof.nodes["speaker_audio"]` | **10** | `audio` | string (file ref) | `"e6f1ac...d595.flac"` | LoadAudio; uploaded speaker reference file |
| (emo_mode selector) | **103** | `value` | int | `-243984737187721` | PrimitiveInt titled "情感模式 selector（1=默认/2=情感文本/3=情感音频/4=情感向量）" |
| (SW_audio) | **104** | `select` | int (from node 103) | wired to 103 | ImpactSwitch routes emo_audio_prompt to IndexTTS2Run |
| (SW_text) | **105** | `select` | int (from node 103) | wired to 103 | ImpactSwitch routes emo_text |
| (SW_vector) | **106** | `select` | int (from node 103) | wired to 103 | ImpactSwitch routes emo_vector |
| (SW_use_text) | **107** | `select` | int (from node 103) | wired to 103 | ImpactSwitch routes use_emo_text |
| `prof.nodes["emo_text"]` | **16** | `prompt` | string | `"高兴"` | CR Prompt Text; emotion text for mode 2 |
| `prof.nodes["emo_audio"]` | **19** | `audio` | string (file ref) | `"ad8f4a...5edf.flac"` | LoadAudio; emotion reference audio for mode 3 |
| `prof.nodes["emo_vector"]` | **21** | `prompt` | string | `"[0, 0, 0, 0, 0, 0, 0.7, 0]"` | CR Prompt Text; emotion vector string for mode 4 |
| IndexTTS2Run (executor) | **1** | `emo_alpha` | float | `1.0` | The single TTS execution node |
| IndexTTS2Run | **1** | `top_k` | int | `30` | Sampling param |
| IndexTTS2Run | **1** | `top_p` | float | `0.8` | Sampling param |
| IndexTTS2Run | **1** | `temperature` | float | `0.8` | Sampling param |
| IndexTTS2Run | **1** | `num_beams` | int | `3` | Sampling param |
| IndexTTS2Run | **1** | `max_mel_tokens` | int | `1500` | Sampling param |
| (save audio) | **5** | `filename_prefix` | string | `"audio/ComfyUI"` | SaveAudio (FLAC) |
| (constants) | **100** | `value` | string | `""` | PrimitiveString constant: empty string |
| (constants) | **101** | `value` | bool | `true` | PrimitiveBoolean constant: True |
| (constants) | **102** | `value` | bool | `false` | PrimitiveBoolean constant: False |
| (note) | **25** | `text` | string | emotion vector legend | Note node; not in execution graph |

### Backend code path
- `drama_shot_master/core/tts_profiles.py`: `VOICE_CLONE` profile maps:
  ```python
  "switch": "27",           # CRITICAL: mismatches actual node 103
  "branch_default": "1",    # Mode 1 -> IndexTTS2Run node 1 (correct)
  "branch_emo_text": "14",  # Mode 2 -> node 14 (DOES NOT EXIST in this JSON)
  "branch_emo_audio": "17", # Mode 3 -> node 17 (DOES NOT EXIST in this JSON)
  "branch_emo_vector": "20" # Mode 4 -> node 20 (DOES NOT EXIST in this JSON)
  ```
- `drama_shot_master/providers/tts_builder.py:build_clone_node_info()` builds nodeInfoList

### Parameter mapping (backend sends via build_clone_node_info)
```python
# Common
{"nodeId": "4",  "fieldName": "prompt", "fieldValue": text}
{"nodeId": "10", "fieldName": "audio",  "fieldValue": speaker_file}
{"nodeId": "27", "fieldName": "select", "fieldValue": mode_index}  # ← node 27 DOES NOT EXIST
{"nodeId": branch_id, "fieldName": "emo_alpha", "fieldValue": emo_alpha}

# Mode 2: emo text
{"nodeId": "16", "fieldName": "prompt", "fieldValue": emo_text}

# Mode 3: emo audio
{"nodeId": "19", "fieldName": "audio", "fieldValue": emo_audio_file}

# Mode 4: emo vector
{"nodeId": "21", "fieldName": "prompt", "fieldValue": "[0, 0, 0, 0, 0, 0, 0.7, 0]"}

# Sampling (appended when present)
{"nodeId": branch_id, "fieldName": "top_k", "fieldValue": 30}
{"nodeId": branch_id, "fieldName": "top_p", "fieldValue": 0.8}
# etc.
```

### CRITICAL DISCREPANCIES (source of errors)

1. **Switch node ID mismatch**: Backend `tts_profiles.py` maps `switch` to `"27"`, but this workflow JSON has **no node 27**. The actual mode selector is `PrimitiveInt` node **103** whose `value` field feeds into all 4 `ImpactSwitch` nodes (104-107) via wiring. To change mode, the backend should set:
   ```python
   {"nodeId": "103", "fieldName": "value", "fieldValue": mode_index}
   ```
   NOT the current:
   ```python
   {"nodeId": "27", "fieldName": "select", "fieldValue": mode_index}
   ```

2. **Branch node IDs mismatch**: Backend `branch_emo_text="14"`, `branch_emo_audio="17"`, `branch_emo_vector="20"` — none of these nodes exist in the current workflow JSON. There is only **one** `IndexTTS2Run` node (node **1**) that handles all modes. The branch selection is done upstream via the ImpactSwitch cascade (nodes 104-107), not by targeting separate IndexTTS2Run nodes.

3. **All 4 modes route through the same IndexTTS2Run (node 1)**: The backend currently sends `emo_alpha` and sampling params to `branch_id` (which resolves to "14", "17", or "20" for modes 2-4). These nodes don't exist — all params should go to node **1**.

4. **Sampling params location**: Config default `dub_sampling` sends `top_k`, `top_p`, `temperature`, `num_beams`, `max_mel_tokens` to `branch_id` — but in this workflow those fields belong to node **1** (`IndexTTS2Run`).

**Suspected root cause**: The workflow deployed on RunningHub (workflow_id `2058388078015901697`) may be a DIFFERENT version than the JSON file saved at `comfyui_workflow/TTS2 情感声音克隆_input_switch_api.json`. The profile node IDs (`tts_profiles.py`) appear to target an older or differently-structured workflow with multiple IndexTTS2Run nodes and a different switch mechanism. If the deployed workflow was updated to use the ImpactSwitch cascade design, the backend must be updated to match.

---

## 3. Ace-Step 1.5X BGM (`Ace-Step1.5X 配乐_api.json`)

| Backend Accessor | node_id | fieldName | Type | Default | Notes |
|---|---|---|---|---|---|
| `NODE_TAGS` | **94** | `tags` | string | `"Instrumental, no vocals..."` | TextEncodeAceStepAudio1.5; long template prompt with tags, style |
| `NODE_BPM` | **203** | `value` | int | `75` | Int node titled "每分钟节拍数" |
| `NODE_DUR` | **205** | `value` | float | `15.0` | Float node titled "歌曲时长（秒）" |
| `NODE_SEED` | **109** | `value` | int | `-1019475144958018` | PrimitiveInt titled "Seed / 随机种子" |
| TextEncodeAceStepAudio1.5 | **94** | `lyrics` | string | `""` | Empty; not overridden |
| TextEncodeAceStepAudio1.5 | **94** | `timesignature` | string | `"4"` | Not overridden |
| TextEncodeAceStepAudio1.5 | **94** | `language` | string | `"zh"` | Not overridden |
| TextEncodeAceStepAudio1.5 | **94** | `keyscale` | string | `"A minor"` | Not overridden |
| TextEncodeAceStepAudio1.5 | **94** | `generate_audio_codes` | bool | `true` | Not overridden |
| TextEncodeAceStepAudio1.5 | **94** | `cfg_scale` | float | `2` | Not overridden |
| TextEncodeAceStepAudio1.5 | **94** | `temperature` | float | `0.85` | Not overridden |
| TextEncodeAceStepAudio1.5 | **94** | `top_p` | float | `0.9` | Not overridden |
| TextEncodeAceStepAudio1.5 | **94** | `top_k` | int | `0` | Not overridden |
| TextEncodeAceStepAudio1.5 | **94** | `min_p` | int | `0` | Not overridden |
| TextEncodeAceStepAudio1.5 | **94** | `seed` | input (from node 109) | wired | Overridden via node 109 |
| TextEncodeAceStepAudio1.5 | **94** | `bpm` | input (from node 203) | wired | Overridden via node 203 |
| TextEncodeAceStepAudio1.5 | **94** | `duration` | input (from node 205) | wired | Overridden via node 205 |
| KSampler | **3** | `seed` | input (from node 109) | wired | Same seed source |
| KSampler | **3** | `steps` | int | `8` | Not overridden |
| KSampler | **3** | `cfg` | float | `1` | Not overridden |
| KSampler | **3** | `sampler_name` | string | `"euler"` | Not overridden |
| Empty Ace Step 1.5 Latent Audio | **98** | `seconds` | input (from node 205) | wired | Duration fed into latent |
| UNETLoader | **104** | `unet_name` | string | `"acestep_v1.5_xl_turbo_bf1s6.safetensors"` | Not overridden |
| DualCLIPLoader | **105** | `clip_name1` | string | `"qwen_0.6b_ace15.safetensors"` | Not overridden |
| DualCLIPLoader | **105** | `clip_name2` | string | `"qwen_4b_ace15.safetensors"` | Not overridden |
| VAELoader | **106** | `vae_name` | string | `"ace_1.5_vae.safetensors"` | Not overridden |
| Save Audio (MP3) | **107** | `filename_prefix` | string | `"audio/ys_acestep15xl_mv_new"` | Not overridden |

### Backend code path
- `sound_track_agent/music_generator.py:generate_bgm()` builds `nodeInfoList` via `_node_info()`

### Parameter mapping (backend sends)
```python
{"nodeId": "94",  "fieldName": "tags",   "fieldValue": user_tags}
{"nodeId": "203", "fieldName": "value",  "fieldValue": bpm}
{"nodeId": "205", "fieldName": "value",  "fieldValue": duration}
{"nodeId": "109", "fieldName": "value",  "fieldValue": seed}
```

### Notable items
- Node IDs match exactly between workflow JSON and backend constants (`NODE_TAGS="94"`, `NODE_BPM="203"`, `NODE_DUR="205"`, `NODE_SEED="109"`)
- The `bpm` parameter overrides node **203** (Int widget "每分钟节拍数"), which is wired into node 94's `bpm` input — correct indirection
- The `duration` parameter overrides node **205** (Float widget "歌曲时长（秒）"), which is wired into BOTH node 94's `duration` AND node 98's `seconds` — correct
- The `seed` parameter overrides node **109** (PrimitiveInt), which is wired into BOTH node 94's `seed` AND node 3 (KSampler)'s `seed` — correct single-point override

---

## 4. Stable Audio 3 SFX (`Stable audio 3纯音乐-音效-VFX-One-Shot音频_api.json`)

| Backend Accessor | node_id | fieldName | Type | Default | Notes |
|---|---|---|---|---|---|
| SFX prompt | **92** | `value` | string (multiline) | `"马嘶鸣，打雷下雨"` | PrimitiveStringMultiline; user short description, `USER_INPUT` placeholder in template |
| SFX duration | **98** | `value` | float | `2.0` | PrimitiveFloat titled "Float (Duration)" |
| Mode index | **108** | `index` | int | `2` | easy anythingIndexSwitch; selects SFX mode (0=Music, 1=Instrument, 2=SFX, 3=One-shot) |
| Seed | **84** | `seed` | int | `197139292951747` | KSampler seed |
| Prompt template | **96** | `string` | string | `"SYSTEM_PROMPTS\n\nInput: USER_INPUT\n..."` | StringReplace node; template with SYSTEM_PROMPTS + USER_INPUT placeholders |
| Reprompt toggle | **97** | `value` | bool | `true` | PrimitiveBoolean; enables LLM reprompt (qwen3.5-4B) |
| LLM generate | **91** | `prompt` | string | (from template chain) | TextGenerate node; qwen3.5-4B transforms short desc into full SFX prompt |
| System prompts JSON | **94** | `json_string` | string (big JSON) | 4-mode prompt templates | JsonExtractString; contains Music/Instrument/SFX/One-shot system prompts |
| KSampler | **84** | `steps` | int | `8` | Not overridden |
| KSampler | **84** | `cfg` | float | `1` | Not overridden |
| KSampler | **84** | `sampler_name` | string | `"lcm"` | Not overridden |
| CheckpointLoaderSimple | **99** | `ckpt_name` | string | `"stable_audio_3_medium.safetensors"` | Not overridden |
| CLIPLoader (qwen) | **85** | `clip_name` | string | `"qwen3.5_4b_bf16.safetensors"` | TextGenerate model |
| CLIPLoader (t5) | **100** | `clip_name` | string | `"t5gemma_b_b_ul2.safetensors"` | SA3 CLIP encoder |
| Empty Latent Audio | **83** | `seconds` | input (from node 98) | wired | Duration into latent generation |

### Backend code path
- `sound_track_agent/sfx/prompt_composer.py:_node_info()` builds `nodeInfoList`
- `sound_track_agent/sfx/generator.py:generate_sfx()` calls `create_task` + `_wait_success`
- `sound_track_agent/overlay_gen.py:_gen_sfx()` wraps with caching

### Parameter mapping (backend sends)
```python
{"nodeId": "92",  "fieldName": "value",  "fieldValue": prompt}
{"nodeId": "98",  "fieldName": "value",  "fieldValue": duration}
{"nodeId": "108", "fieldName": "index",  "fieldValue": 2}
{"nodeId": "84",  "fieldName": "seed",   "fieldValue": seed}
```

### Notable items
- Node IDs match exactly between workflow JSON and backend constants
- The workflow has an LLM reprompt layer: short user description (node 92) → placeholder replacement (node 90) → LLM TextGenerate (node 91, qwen3.5-4B) → CLIPTextEncode (node 86) → KSampler. The backend overrides node 92 (the raw user input), and the workflow automatically expands it through the LLM chain
- Mode index 2 = SFX (from the 4-mode JSON: Music=0, Instrument=1, SFX=2, One-shot=3)
- Duration is limited to 1-15s by the backend (`_SFX_MIN_DUR=1.0`, `_SFX_MAX_DUR=15.0`)
- The `sfx_workflow_id` in config defaults to `"2060218796413112321"`

---

## Summary: Backend-to-Workflow Node ID Verification

| Workflow | Parameter | Backend node_id | JSON node_id | Match? |
|---|---|---|---|---|
| Qwen3 TTS Voice Design | text | 14 | 14 | OK |
| Qwen3 TTS Voice Design | style (instruct) | 15 | 15 | OK |
| Qwen3 TTS Voice Design | language | 22 | 22 | OK |
| Qwen3 TTS Voice Design | **speed** | (not used) | (does not exist) | N/A |
| TTS2 Clone | text | 4 | 4 | OK |
| TTS2 Clone | speaker_audio | 10 | 10 | OK |
| TTS2 Clone | **emo_mode switch** | **27** | **103** | MISMATCH |
| TTS2 Clone | emo_text | 16 | 16 | OK |
| TTS2 Clone | emo_audio | 19 | 19 | OK |
| TTS2 Clone | emo_vector | 21 | 21 | OK |
| TTS2 Clone | branch_default | 1 | 1 | OK (one IndexTTS2Run) |
| TTS2 Clone | **branch_emo_text** | **14** | **(missing)** | MISMATCH |
| TTS2 Clone | **branch_emo_audio** | **17** | **(missing)** | MISMATCH |
| TTS2 Clone | **branch_emo_vector** | **20** | **(missing)** | MISMATCH |
| Ace-Step BGM | tags | 94 | 94 | OK |
| Ace-Step BGM | bpm | 203 | 203 | OK |
| Ace-Step BGM | duration | 205 | 205 | OK |
| Ace-Step BGM | seed | 109 | 109 | OK |
| Stable Audio 3 SFX | prompt | 92 | 92 | OK |
| Stable Audio 3 SFX | duration | 98 | 98 | OK |
| Stable Audio 3 SFX | mode index | 108 | 108 | OK |
| Stable Audio 3 SFX | seed | 84 | 84 | OK |

### Key findings

1. **Qwen3 TTS** has no `speed` parameter. If speed variation is needed, the workflow or the TDQwen3TTSVoiceDesign node must be updated to expose one.

2. **TTS2 Clone has the most critical discrepancy**: The `switch` node is mapped to node `"27"` in `tts_profiles.py` but the actual workflow uses node `"103"` (PrimitiveInt) to control the mode. Additionally, `branch_emo_text="14"`, `branch_emo_audio="17"`, and `branch_emo_vector="20"` do not exist in this workflow — there is only one `IndexTTS2Run` node (1). The backend sends `emo_alpha` and sampling params to non-existent nodes for modes 2-4. Either the RunningHub-deployed workflow differs from this JSON, or the backend profile is stale.

3. **Ace-Step BGM** and **Stable Audio 3 SFX** mappings are fully correct and verified against their workflow JSONs.
