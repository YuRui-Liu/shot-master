# 智能配音 + 智能配乐 Code Review 报告

> 审查日期: 2026-06-01 | 5 个机器人并行审查

---

## 配音 (Dubbing) 审查发现

### P0 — 阻塞级

| # | 发现 | 文件:行 | 影响 |
|---|------|---------|------|
| 1 | **language 值不一致**: design 模式发 `"zh"`, clone 模式发 `"中文"`, 后端默认 `"中文"` | dub-mode2:657,1166,1403; tts.py:72 | design 模式 TTS 可能静默失败 |
| 2 | **TTS 请求无超时**: fetch 没有 AbortController, RunningHub 挂起时按钮永远 disabled | dub-mode2:1178,1432 | 用户无法取消或重试 |
| 3 | **后端未校验 speaker_file 存在性**: `Path(req.speaker_file)` 不检查 `.exists()` | tts.py:125-129 | 文件不存在时抛 502 而非 400 |
| 4 | **KeyError/OSError 未捕获**: `_do_synthesize` 只有 3 个 except 分支, KeyError(上传失败)和 OSError(路径非法)穿透到 FastAPI 500 | tts.py:143-170 | 部分错误返回裸 traceback |
| 5 | **speed/sampling 在 design 模式被丢弃**: `build_design_node_info()` 不接收 sampling 参数 | tts.py:108-116 → tts_builder.py | 用户调 speed 无效 |
| 6 | **Mode 2 clone 无 sampling 控件**: mode1 有 temperature/top_p/top_k, mode2 完全没有 | dub-mode2:1075-1106 | 两模式功能不一致 |

### P1 — 严重级

| # | 发现 | 文件:行 |
|---|------|---------|
| 7 | **emo_vector 后端零校验**: Pydantic 模型不检查长度(应为8)/类型(应为float)/范围(0-1.2) | tts.py:82 |
| 8 | **mode2 无 sampling UI**: 每镜卡片只有 voice/emotion/speed, 缺 temperature/top_p/top_k | dub-mode2:806-819 |
| 9 | **任务无持久化**: m1Tasks/PARALLEL_TASKS 纯内存, 页面刷新丢失 | dub-mode2:1265,663 |
| 10 | **localStorage 损坏静默吞错**: `catch {}` 空块, 用户无感知, 坏数据不清理 | dub-mode2:1234 |

### 安全

| # | 发现 | 文件:行 |
|---|------|---------|
| 11 | **speaker_file 无沙箱**: 可上传任意系统文件到 RunningHub | tts.py:125 |
| 12 | **out_dir 无边界检查**: 可写任意路径 | tts.py:103-104; soundtrack.py:216 |
| 13 | **用户文本未转义 XSS**: `dub-mode2.html` 没有 `esc()` 函数, shot.line 直接插 innerHTML | dub-mode2:730,1650 |

---

## 配乐 (Soundtrack) 审查发现

### P0 — 阻塞级

| # | 发现 | 文件:行 | 影响 |
|---|------|---------|------|
| 1 | **analyze_segment 不校验 video 路径**: 空字符串/不存在的文件 → ffmpeg 失败 → 500 | soundtrack.py:140-176 | 错误信息无意义 |
| 2 | **overlay/advance/mixdown 只捕获 ValueError**: 网络超时/磁盘满/ffmpeg 崩溃全变 500 | soundtrack.py:231-234,473,586-592 | 大量异常穿透 |
| 3 | **work_dir 无校验**: 所有端点不检查 work_dir 是否存在/可写 | soundtrack.py:多处 | 深层内部错误返回 500 |

### P1 — 严重级

| # | 发现 | 文件:行 |
|---|------|---------|
| 4 | **PX_PER_SEC 双重硬编码**: CSS `--pps:58px` + JS `const PX_PER_SEC = 58`, 不同步风险 | daw-soundtrack:88,298 |
| 5 | **loadOverlayList 吞所有错误**: 空 catch 块抑制网络错误/500/格式错误 | daw-soundtrack:814-821 |
| 6 | **generateOverlay 缺 else 分支**: 后端返回无 segment 字段时静默忽略 | daw-soundtrack:694-703 |

### 并发

| # | 发现 | 文件:行 |
|---|------|---------|
| 7 | **session.json 无原子写入**: `Path.write_text()` 直接覆盖, 并发写 → 最后胜出/文件损坏 | soundtrack.py:多处 |
| 8 | **BGM 缓存无锁**: 两线程同时查缓存 → 双调 RunningHub | batch_generator.py:28-44 |
| 9 | **FastAPI sync 端点无法取消**: 用户断连后服务器继续消耗资源 | soundtrack.py, tts.py:全部 def 端点 |

---

## 修复建议优先级

1. **立即修**: 配音 language 不一致 + speed 丢弃 + 500 异常透传 + XSS
2. **本次迭代**: work_dir 校验 + path 存在性检查 + emo_vector 校验
3. **下个迭代**: 任务持久化 + 请求超时 + 并发锁 + API key 不暴露
