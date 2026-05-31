# 实施计划 — 框选生成交互 #3d

> Spec：`docs/superpowers/specs/2026-05-31-overlay-framing-generate-design.md`
> 交互确认：`docs/explorer/3d-framing-generate-interaction-confirm.html`（4 决策全取推荐默认）
> 方法：TDD。**前置：3c 已合并**（D6/D7 依赖 3c 渲染 + `_refresh_overlay_view`）。

## 依赖图

```
D1 status 字段(3a) ─┐
D2 suggest_prompt ──┤(各自独立可并行)
D3 generate_clip ───┼──▶ D5 GenWorker(依赖D3) ─┐
D4 GenerateDialog ──┘                          ├─▶ D7 editor 接线(整合, 依赖3c)
                         D6 TrackView status 上色(依赖3c) ─┘
```

## D1 — OverlaySegment.status（3a 小扩展）

**改** `sound_track_agent/overlay_session.py`、`tests/test_sound_track_agent/test_overlay_session.py`

- RED：测 `add(..., status="generating")`→seg.status；`to_dict` 含 status；`from_dict` 缺 status→"generated"（迁移）；round-trip 保留 status。
- GREEN：`OverlaySegment` 加 `status: str = "generated"`；`add` 加 `status="generated"` 参数透传；to_dict/from_dict 同步。
- 验证：`pytest tests/test_sound_track_agent/test_overlay_session.py -q`。

## D2 — suggest_overlay_prompt（LLM 建议，可降级）

**新增** `sound_track_agent/overlay_prompt.py`、`tests/test_sound_track_agent/test_overlay_prompt.py`

- RED：mock LLM provider 返回文本→透传去空白；provider 抛/未配置→返回 ""。
- GREEN：参考现有 provider 取法（grep translator/screenwriter 的 LLM 平台配置入口）；组 prompt（kind+对白字幕+global_style）→ 调一次 → 返回；try/except 全降级 ""。
- 验证：`pytest tests/test_sound_track_agent/test_overlay_prompt.py -q`。

## D3 — generate_overlay_clip（单片段生成，复用现有管线）

**新增** `sound_track_agent/overlay_gen.py`、`tests/test_sound_track_agent/test_overlay_gen.py`

- RED（注入假 client / 假缓存，不碰网络）：BGM→走 `music_generator.generate_bgm(tags=prompt,...)` 取首结果返回 Path；SFX→`sfx.generator.generate_sfx(prompt, duration, seed, out_path)`；duration<1 或 >15(SFX) 被 clamp；生成异常上抛。
- GREEN：`generate_overlay_clip(kind, prompt, duration, *, work_dir, cfg, client=None)`；按 kind 分派；复用 `audio_cache`(cache_key/sfx_cache_key + store)；client 缺省自建 RunningHubClient。
- 验证：`pytest tests/test_sound_track_agent/test_overlay_gen.py -q`。

## D4 — GenerateOverlayDialog

**新增** `drama_shot_master/ui/dialogs/generate_overlay_dialog.py`、`tests/test_ui/dialogs/test_generate_overlay_dialog_smoke.py`（test_ui/dialogs/ 无则建 + `__init__.py`）

- RED：构造(t_start=10,t_end=18)→时长 label 含 "8"；切 SFX→kind="sfx"；注入同步 stub `suggest_fn` 返回 "xx"→prompt 预填 "xx"；填 prompt+接受→`result_value()==("bgm","...")`；取消→None。
- GREEN：QDialog：BGM/SFX QButtonGroup + QPlainTextEdit + 只读时长 label + 生成/取消。构造后用 QTimer.singleShot(0) 或 QThreadPool 异步调 suggest_fn 预填（不阻塞）；测试用同步路径可断言。参考 `drama_shot_master/ui/dialogs/prompt_edit_dialog.py` 风格。
- 验证：`pytest tests/test_ui/dialogs/test_generate_overlay_dialog_smoke.py -q`。

## D5 — OverlayGenWorker（异步生成，依赖 D3）

**新增** `drama_shot_master/ui/widgets/daw/overlay_gen_worker.py`、`tests/test_ui/daw/test_overlay_gen_worker.py`

- RED：注入假 `generate_overlay_clip`（直接返回 Path）→ run→`finished(seg_id, path)` 发；注入抛异常→`failed(seg_id, err)` 发。用 QSignalSpy；不依赖真网络。
- GREEN：`OverlayGenWorker(QObject)` 持 (seg_id, kind, prompt, duration, work_dir, cfg)；`run()` 调 `generate_overlay_clip` try/except → 发 finished/failed。可 QThreadPool(QRunnable 包装) 或 QThread。
- 验证：`pytest tests/test_ui/daw/test_overlay_gen_worker.py -q`。

## D6 — DawTrackView 片段按 status 上色（扩展 3c，依赖 3c 已合并）

**改** `drama_shot_master/ui/widgets/daw/daw_track_view.py`、新增/扩展 `tests/test_ui/daw/test_daw_track_view_overlay.py`

- RED：纯函数 `_overlay_block_style(status)`→generating/failed/generated 各返回不同(色,文案前缀)；set_overlay 含三态 segment 不崩。
- GREEN：在 3c overlay 片段绘制处按 `seg.status` 取色：generating→脉冲/灰斜纹 + "⟳"；failed→红斜纹 + "✕"；generated→原色。抽 `_overlay_block_style` 纯函数。
- 验证：`pytest tests/test_ui/daw/ -q`（不回归 3c）。

## D7 — SoundtrackEditor 接线（整合，依赖 3c + D1–D6）

**改** `drama_shot_master/ui/widgets/soundtrack_editor.py`、**新增** `tests/test_ui/test_soundtrack_overlay_framing_wiring.py`

- RED（mock 重组件）：
  - `_on_rubber_band(rect,mod)`：mock dialog 返回 ("bgm","p")→`_overlay_session` 多一个 status=="generating" 段 + `save_overlay` 被调 + worker 被起（mock OverlayGenWorker）；mock dialog 返回 None→无 add、无 worker。
  - worker finished 槽：seg.audio_path/status="generated" 更新 + `mix_engine.set_segments` 被调 + 刷新。
  - worker failed 槽：seg.status="failed" + 刷新。
- GREEN：
  - `_gen_overlay_id(kind)`（毫秒戳+hex）。
  - `_on_rubber_band` 实装：`_x_to_t` 算区间 → `GenerateOverlayDialog` exec → add 占位(status="generating")→ save_overlay → `_refresh_overlay_view` → 起 `OverlayGenWorker`（存引用防 GC）连 finished/failed 槽。
  - finished/failed 槽按 spec 更新 session + save + set_segments + 刷新；seg 已删则丢弃。
  - 失败重试入口（inspector 或 failed 块）。
- 验证：
  - `pytest tests/test_ui/test_soundtrack_overlay_framing_wiring.py -q`
  - 回归：`pytest tests/test_ui -q`、`pytest tests/test_sound_track_agent -q`。

## 收尾

- 全量绿；手动确认交互稿与实现一致（框选→对话框→生成中占位→完成/失败）。
- 提交：spec+plan 一次 `docs(...)`；D1–D7 各一次 `feat(soundtrack): ... 子项目#3d-N`。
- 做完 3d → 项目 #3「框选→生成→叠加多子轨」完结。
