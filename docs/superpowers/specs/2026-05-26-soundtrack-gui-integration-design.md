# 配乐功能接入导演台 · 设计

> 日期：2026-05-26
> 目标：把已完成的 `sound_track_agent`（成片 MP4 → BGM 配乐）以**顶部"配乐"tab**接入 drama-shot-master，保持 agent 相对独立、日后可整包拆除而不影响宿主。

---

## 1. 目标与约束（已确认）

| 维度 | 结论 |
|---|---|
| 功能 | **配乐（BGM）**：给成片自动配背景音乐 + 避让对白。接入现有 `sound_track_agent`（非 TTS 对白配音） |
| 入口 | 主窗口顶部新增 **"配乐" tab**（与 反推/拆图/拼图/去白边/视频生成 并列） |
| 范式 | 复用视频生成的 **"任务列表 + 任务窗"** 模式：tab 内是任务列表，双击打开单集配乐任务窗 |
| 可拆边界 | **薄适配层 + 一处注册**。拆除 = 删 agent 包 + 删两个 UI 文件 + 删 main_window 一处 try-import 块。宿主其余零改动 |
| facade 位置 | **agent 包内** `sound_track_agent/facade.py`（agent 自带对外门面；读宿主 cfg 属性但不 import 宿主） |
| 交互 | 目标完整半自动；**分期**：第一期骨架（任务列表+一键出片+生成后暂停点），第二期重 UI（试听选优+卡点编辑） |
| 线程 | 配乐是长任务，复用宿主 `FunctionWorker` 搬后台，进度经 `QTimer.singleShot` 回主线程（同 video_panel） |

## 2. 架构：可拆性的三道边界

```
┌─ drama_shot_master（宿主，几乎零改）────────────────────────┐
│  main_window.py                                              │
│    FUNCS += ("配乐","soundtrack")        ← 改动点 1（一行）   │
│    panels += [_try_make_soundtrack_panel()]  ← 改动点 2       │
│        （try-import，agent 缺失则跳过该 tab，宿主照常启动）   │
│  ui/panels/soundtrack_panel.py           ← 新增（可删）       │
│  ui/windows/soundtrack_task_window.py    ← 新增（可删）       │
└──────────────────────────┬───────────────────────────────────┘
                           │ 只调用 facade 的 2 个函数
┌──────────────────────────▼─ sound_track_agent（独立包）──────┐
│  facade.py   prepare_session / advance   ← 唯一对外门面       │
│  （内部 build_soundtrack_provider(cfg)+RunningHubClient,      │
│    detect_shots→plan_segments→build_stages→pipeline.run）     │
│  其余 13 个模块：零宿主依赖                                   │
└───────────────────────────────────────────────────────────────┘
```

**三道边界保证可拆：**
1. **GUI→agent 只经 facade 两函数**：agent 内部重构不影响面板。
2. **facade 读 cfg 用鸭子类型**：只 `getattr(cfg, "refine_api_key", ...)` 等，不 `import drama_shot_master` → agent 包可整体搬到别的项目。
3. **main_window 用 try-import 降级**：`sound_track_agent` 删掉后，那个 tab 不出现，宿主正常启动、其余功能无感。

## 3. facade 接口（GUI 与 agent 的唯一边界）

`sound_track_agent/facade.py`：

```python
def prepare_session(mp4: str | Path, style: str, work_dir: str | Path,
                    *, cfg) -> ScoringSession:
    """MP4 → 切镜头 → 段落聚合 → 新建 ScoringSession（不调豆包/ACE-Step，快）。
    供 GUI 先拿到段落结构显示。source_hash=hash_file(mp4)。"""

def advance(session: ScoringSession, work_dir: str | Path, *, cfg,
            workflow_id: str, seeds_count: int = 2,
            stop_after: str = "mix",
            on_progress: Callable[[str], None] | None = None) -> ScoringSession:
    """从 session 当前状态推进到 stop_after，返回推进后的 session（到 mix 时含 output）。
    可重复调用 = 续跑（pipeline 幂等跳过已完成阶段）。每阶段落盘到 work_dir/session.json。"""
```

要点：
- facade **不 import 任何 `drama_shot_master`**；`cfg` 鸭子类型，读 `refine_api_key/refine_base_url/refine_model`（供 `build_soundtrack_provider`）、`runninghub_api_key/runninghub_base_url`（建 `RunningHubClient`）。
- `prepare`/`advance` 分离 = 半自动暂停点接口基础：GUI 可 prepare（显示段落）→ advance(stop_after="generate")（停在选优）→ advance(stop_after="mix")（出片）。
- `on_progress(msg)` 在 worker 线程被调用；GUI 转发到进度条/状态栏。
- `frame_provider`/`mix_fn` 由 facade 内部用 `mixdown.extract_segment_frame`/`assemble_and_mix` 偏函数注入（GUI 不感知）。

## 4. UI 组件（第一期骨架）

### 4.1 SoundtrackPanel（`ui/panels/soundtrack_panel.py`，BasePanel 子类）

任务列表，复用 `VideoTaskManagerPanel` 模式：
- `QTableWidget`：名称 / 成片MP4 / 状态 / 输出；状态色标沿用 `_STATUS_COLORS`（空闲灰/生成中蓝/完成绿/失败红）。
- 按钮：+ 新建配乐任务 / 打开 / 删除。
- `select_mode()→"none"`，`validate()→(False,"用列表内按钮管理")`，`execute()` 不用（同 VideoTaskManagerPanel）。
- 任务持久化：复用宿主 config 落盘（新增 `cfg.soundtrack_tasks` 字段，结构同 `video_tasks`）。开窗/关窗/持久化回调由 main_window 提供（同视频范式）。

### 4.2 SoundtrackTaskWindow（`ui/windows/soundtrack_task_window.py`，QMainWindow）

单集配乐任务窗（第一期）：
- 表单：成片 MP4（浏览）/ 总风格（多行）/ Workflow ID（默认 `2059090557116440578`）/ 候选数（默认 2）/ "停在"单选（stop_after）。
- 段落预览区：`prepare_session` 后填充各段 start–end / 情绪 / prompt 概览。
- 「🎬 开始配乐」→ `FunctionWorker` 跑 `facade.prepare_session` 然后 `facade.advance(stop_after)`；`on_progress` 经 `QTimer.singleShot(0, ...)` 刷进度条。
- 完成发信号给 panel 更新列表状态（生成中/完成/失败）。

### 4.3 第二期（本设计记录，不在第一期实现）

在 SoundtrackTaskWindow 内追加：
- **试听选优区**：每段 2-4 候选，`QMediaPlayer` 内嵌播放 + 波形；选定写 `SegmentScore.chosen_candidate`，再 `advance(stop_after="mix")`。
- **卡点编辑区**：可视化 `session.accent_points`，增删/微调时间戳。

## 5. 数据流

```
新建任务（名称+MP4+风格）→ 存 cfg.soundtrack_tasks
  ↓ 双击打开任务窗
开始配乐 → worker 线程：
  facade.prepare_session(mp4,style,work_dir,cfg) → ScoringSession（段落填充回 UI）
  facade.advance(session, stop_after="generate", on_progress=...) → 各段候选生成、落盘
  ↓（第一期：默认取首候选；第二期：人工试听选优）
  facade.advance(session, stop_after="mix") → 拼接+分离+ducking+写回 → output mp4
  ↓
finished_with_result → 更新列表状态=完成、输出路径；失败 → failed → 状态=失败
```

## 6. 错误处理 / 降级

- **agent 缺失**：main_window 的 `_try_make_soundtrack_panel` 用 try-import，`ImportError` → 不加该 tab、打日志，宿主正常启动。
- **重型库缺失**（cv2/scenedetect/librosa/demucs/ffmpeg 未装）：facade 调用时抛 ImportError/RuntimeError → worker `failed` 信号 → 任务窗弹错误 + 列表状态=失败，不崩宿主。
- **RunningHub/豆包 凭据缺失或失败**：facade 内 client/provider 调用抛异常 → 同上走 failed。
- **长任务取消**：任务窗持 cancel flag（同 video_panel `_cancel_flag` 模式），传入 `pipeline` 轮询检查（facade 暴露 cancel_check 可选参数）。

## 7. 测试策略

- **facade 单测**（`tests/test_sound_track_agent/test_facade.py`）：mock cfg（鸭子类型最小对象）+ mock RunningHubClient/provider + 极小合成 MP4，验证 prepare 产出段落、advance 推进 + on_progress 被调用、stop_after 生效。重型服务 mock，编排真跑。
- **UI 面板**：宿主无 GUI 单测惯例（PySide 难自动测），靠 offscreen 构造冒烟（`QT_QPA_PLATFORM=offscreen` 能 import+实例化面板不崩）+ 人工验证。
- **可拆验证**：删 `sound_track_agent/` 后跑宿主 offscreen 启动，确认 try-import 降级、其余 tab 正常。

## 8. 改动清单（第一期）

| 文件 | 改动 |
|---|---|
| `sound_track_agent/facade.py` | 新增（prepare_session + advance） |
| `drama_shot_master/ui/panels/soundtrack_panel.py` | 新增（任务列表面板） |
| `drama_shot_master/ui/windows/soundtrack_task_window.py` | 新增（单集任务窗骨架） |
| `drama_shot_master/ui/main_window.py` | FUNCS 加一项 + panels try-import 注册一处 |
| `drama_shot_master/config.py` | 加 `soundtrack_tasks` 字段（持久化，结构同 video_tasks） |
| `tests/test_sound_track_agent/test_facade.py` | 新增（facade 单测） |

## 9. 实现时定（不阻塞设计）

- `cfg.soundtrack_tasks` 的具体 schema（参考 `video_tasks` 现有结构定）。
- 任务窗"停在"默认值（建议 `generate`，让用户养成选优习惯；第一期选优自动取首候选）。
- cancel_check 是否第一期就接（建议接，长任务必要）。

## 10. 一句话总结

顶部"配乐"tab → 任务列表 → 单集任务窗（选 MP4+风格 → 一键经 facade.prepare/advance 后台跑到出片，带进度与暂停点）；GUI 只依赖 `sound_track_agent/facade.py` 两个函数 + main_window 一处 try-import 注册，agent 包零宿主依赖，删除即拆、宿主无感。
