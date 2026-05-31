# M0 后端收口 — 本地 media_agent FastAPI 服务

> GUI Web 重构（[[gui-web-rewrite-strategy]]）的第一步。与最终壳选择无关、纯增值、可独立验证。
> 目标：把 imaging/转场/出图/批量/配乐 收口进一个本地 FastAPI（镜像 screenwriter_agent 模式），
> 暴露 REST + SSE，做到「**无 Qt 也能跑通全部后端能力**」（curl/pytest 验证）。

**镜像模板**：`screenwriter_agent/`（server.py create_app+uvicorn 端口回退 / routes/ 分能力 / core/sse.py / routes/health.py nonce）。
**SSE 契约**：对齐 `drama_shot_master/core/task_runner.py` 的 `TaskEvent{type: progress|item_done|complete, payload}`。
**端口**：18450 起（避开 screenwriter 18430-18439）。**安全**：127.0.0.1 + `MEDIA_AGENT_NONCE` env。

## 范围与增量

- [x] **删 `imaging/loader.py` 的 `pixmap_thumbnail` QPixmap 字段** → imaging 彻底零 Qt（无人引用，安全）。
- [x] **增量 1**（a0025b9）：`media_agent` 脚手架 + imaging split/trim/combine + batch_split SSE + 无 Qt 测试。
- [x] **增量 2**（74be46a）：imaging 自动检测 infer_grid/detect_borders/cell_boxes + aspect 居中裁剪。
- [x] **增量 3**（8e6f601）：转场 analyze(CV) / ffmpeg_args(干跑) / render。
- [x] **增量 4**（9161301）：出图 generate / batch_generate SSE，provider 工厂可注入测试。
- [ ] **增量 5**：配乐（`sound_track_agent` — 25+ 模块大流水线，有 facade.py/cli.py）。**需先吃透 facade.py/pipeline.py 再包 FastAPI**：BGM 生成(ACE-Step)/SFX/mixdown/卡点对齐/overlay/session。依赖网络+会话态，是 M0 最大一块，单独聚焦做。
- [ ] **收尾**：OpenAPI 导出为前端契约；`media_agent` 纳入 lifecycle spawn（与 screenwriter_agent 同形，未来由 Web 壳接管）。

**当前 media_agent 已挂载路由**：health / imaging(split/trim/combine/infer_grid/detect_borders/cell_boxes/crop_aspect/batch_split) / transition(analyze/ffmpeg_args/render) / imggen(generate/batch_generate)。全部 16 测试绿、零 Qt 验证过。

## 端点契约（增量 1）

- `GET /health` → `{status, version, pid, nonce}`
- `POST /imaging/split` `{src_path, src_rows, src_cols, sub_rows, sub_cols, margins{t,r,b,l}, gap, target_aspect{w,h}, out_dir, base_name, fmt}` → `{outputs:[path...]}`
- `POST /imaging/trim` `{src_path, threshold, max_iter, out_path, fmt}` → `{output}`
- `POST /imaging/combine` `{src_paths[], target_rows, target_cols, gap, target_aspect{w,h}, scale_mode, out_path, fmt}` → `{output}`
- `POST /imaging/batch_split` `{items:[SplitRequest...]}` → SSE：`event: progress|item_done|complete`（对齐 TaskEvent）

## 验证

- `tests/test_media_agent/` 用 FastAPI `TestClient`（**不导入任何 Qt**）跑 health/split/trim/combine/batch_split。
- 子进程断言零 Qt：`python -c "import media_agent.server,sys; assert 'PySide6' not in sys.modules"`。
