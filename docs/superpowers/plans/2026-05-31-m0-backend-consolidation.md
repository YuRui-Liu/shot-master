# M0 后端收口 — 本地 media_agent FastAPI 服务

> GUI Web 重构（[[gui-web-rewrite-strategy]]）的第一步。与最终壳选择无关、纯增值、可独立验证。
> 目标：把 imaging/转场/出图/批量/配乐 收口进一个本地 FastAPI（镜像 screenwriter_agent 模式），
> 暴露 REST + SSE，做到「**无 Qt 也能跑通全部后端能力**」（curl/pytest 验证）。

**镜像模板**：`screenwriter_agent/`（server.py create_app+uvicorn 端口回退 / routes/ 分能力 / core/sse.py / routes/health.py nonce）。
**SSE 契约**：对齐 `drama_shot_master/core/task_runner.py` 的 `TaskEvent{type: progress|item_done|complete, payload}`。
**端口**：18450 起（避开 screenwriter 18430-18439）。**安全**：127.0.0.1 + `MEDIA_AGENT_NONCE` env。

## 范围与增量

- [x] **删 `imaging/loader.py` 的 `pixmap_thumbnail` QPixmap 字段** → imaging 彻底零 Qt（无人引用，安全）。
- [x] **增量 1（本次）**：`media_agent` 脚手架（config/__init__/core.sse/server/health）+ imaging 同步端点（split/trim/combine）+ 一个 SSE 批量端点（batch_split 走 TaskRunner）+ 无 Qt TestClient 测试。
- [ ] **增量 2**：imaging 自动检测端点（detect_borders/infer_grid）+ aspect 裁剪；批量 trim/combine 的 SSE。
- [ ] **增量 3**：转场（`core/transition_analyzer` 分析 + `transition_render` 渲染）端点（分析快→JSON；渲染慢→SSE 进度）。
- [ ] **增量 4**：出图（`providers/image_gen`）端点 + 批量出图 SSE（复用 TaskRunner）。
- [ ] **增量 5**：配乐（`sound_track_agent` pipeline 包一层 FastAPI：mixdown/SFX/转场配乐）。
- [ ] **收尾**：OpenAPI 导出为前端契约；`media_agent` 纳入 lifecycle spawn（与 screenwriter_agent 同形，未来由 Web 壳接管）。

## 端点契约（增量 1）

- `GET /health` → `{status, version, pid, nonce}`
- `POST /imaging/split` `{src_path, src_rows, src_cols, sub_rows, sub_cols, margins{t,r,b,l}, gap, target_aspect{w,h}, out_dir, base_name, fmt}` → `{outputs:[path...]}`
- `POST /imaging/trim` `{src_path, threshold, max_iter, out_path, fmt}` → `{output}`
- `POST /imaging/combine` `{src_paths[], target_rows, target_cols, gap, target_aspect{w,h}, scale_mode, out_path, fmt}` → `{output}`
- `POST /imaging/batch_split` `{items:[SplitRequest...]}` → SSE：`event: progress|item_done|complete`（对齐 TaskEvent）

## 验证

- `tests/test_media_agent/` 用 FastAPI `TestClient`（**不导入任何 Qt**）跑 health/split/trim/combine/batch_split。
- 子进程断言零 Qt：`python -c "import media_agent.server,sys; assert 'PySide6' not in sys.modules"`。
