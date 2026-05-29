# 编剧任务栏化（ScreenwriterPanel 改造）设计 Spec

**日期：** 2026-05-29
**作者：** Brainstorm pass with user
**状态：** Draft → 待用户最终审阅

---

## 1. 背景与目标

当前 `ScreenwriterPanel`（`drama_shot_master/ui/panels/screenwriter_panel.py`）是「单项目 4 阶段 wizard」MVP 占位：项目目录在设置里固定，wizard 直接显示该项目的产物。这与 Dub / ImgGen / Soundtrack / Video 五个面板使用的「左任务栏 + 右编辑器」`TaskWorkspacePage` 范式不一致。

**目标：** 把 `ScreenwriterPanel` 改造为同款范式。左侧任务栏管理多个编剧项目，每个项目独立维护 4 阶段产物（创意.json / 剧本.md / 分镜.json / prompts/）；右侧 wizard 在用户切换任务时 `set_project()` 重新加载。多个项目可同时跑 SSE 生成，互不打断。

**关键约束：**
- 复用已实现的 4 个子面板 (`IdeatePage` T5 / `ScriptPage` T6 / `StoryboardPage` T8 / `PromptsPage` T10)
- 保留 PySide6（无 GPL 依赖）
- 沿用 `TaskWorkspacePage` 现有 splitter + manager + detail stack 模式

---

## 2. 架构

```
ScreenwriterPanel (QWidget, replaces MVP placeholder)
  └ QSplitter (horizontal, [300, ...])
      ├ ScreenwriterTaskManager  (QWidget, left, maxWidth 300)
      │   ├ Toolbar: [+ 新建] [📂 打开] [🗑 删除]
      │   └ QTableWidget cols: 名称 | 状态点 | 当前阶段 | 更新时间
      │   └ Signals: taskSelected(Path|None), projectAdded(Path), projectRemoved(Path)
      └ ScreenwriterWizardHost   (QWidget, right)
          ├ Stage stepper: [创意] [剧本] [分镜] [提示词]  (可点切换, unconditional)
          └ QStackedWidget (4 子面板单例)
              ├ IdeatePage     (已实现, 改造)
              ├ ScriptPage     (已实现, 改造)
              ├ StoryboardPage (已实现, 改造)
              └ PromptsPage    (T10 实现, 设计时已知签名)
```

**数据流：**
1. `ScreenwriterTaskManager.refresh()` 读 `cfg.screenwriter_projects: list[str]` + 即时扫每个项目目录 → 渲染表格
2. 用户点列表行 → emit `taskSelected(Path)` → `ScreenwriterPanel` 先依次问每个 page `try_release()`，全 OK 才统一调 `set_project(path)`
3. 用户点 stage stepper → `QStackedWidget.setCurrentIndex()`，无条件、不调 `try_release`
4. 子面板的 worker 全存在 page 自身的 `dict[Path, StreamWorker]`；按当前 `_project_dir` 取活跃 worker；切换不杀别项目 worker
5. SSE 事件：worker 自带 `project_dir` 参数，page 收到 if 不是当前显示项目 → 仍累 buffer + 落盘 + emit `projectStateChanged`，但不动 UI

---

## 3. 任务栏（左）

### 3.1 列布局

| 列序 | 标题 | 内容 | 宽度策略 |
|---|---|---|---|
| 0 | 名称 | 项目目录名（如 `躺平农夫`） | 伸缩（`_fit_name_col`，min 100） |
| 1 | 状态点 | `✓✓○○`（4 字符紧凑） | 固定 ~50 |
| 2 | 当前阶段 | `分镜中` / `已完成` / `空项目` | ResizeToContents |
| 3 | 更新时间 | `5 分钟前` / `2026-05-29 09:06` | ResizeToContents |

### 3.2 状态点字符约定

- `○` (U+25CB) — 未开始
- `✓` (U+2713) — 已完成
- `●` (U+25CF) — 进行中（蓝色；用 `QTableWidget.setCellWidget(row, 1, QLabel)` + RichText `<span style='color:#4a9eff'>●</span>` 染色，不写 delegate 以降低复杂度）
- `✗` (U+2717) — 失败（红色）

阶段 → 文件映射：
- 创意 ↔ 项目根/创意.json
- 剧本 ↔ 项目根/剧本.md
- 分镜 ↔ 项目根/分镜.json
- 提示词 ↔ 项目根/prompts/ 目录非空

### 3.3 「当前阶段」推断

1. 任一阶段正在 stream（`page.is_streaming(path)` True）→ `[阶段名] 中`（蓝色）
2. 任一阶段失败（page 持 `_error_by_project`）→ `[阶段名] 失败`（红色）
3. 4 阶段全 ✓ → `已完成`
4. 否则 → `待 [下一未完成阶段]`

### 3.4 工具栏行为

#### 新建（`[+ 新建]`）

```python
def _on_new_clicked(self):
    name, ok = QInputDialog.getText(self, "新建编剧项目", "项目名：")
    if not ok or not name.strip():
        return
    base = Path(self._cfg.screenwriter_project_root or Path.home() / "drama-projects")
    new_dir = base / name.strip()
    if new_dir.exists():
        QMessageBox.warning(self, "同名", f"{new_dir} 已存在"); return
    new_dir.mkdir(parents=True)
    self._add_project(new_dir)
```

#### 打开（`[📂 打开]`）

```python
def _on_open_clicked(self):
    d = QFileDialog.getExistingDirectory(self, "选择项目目录")
    if not d: return
    p = Path(d)
    if p in self._projects:
        QMessageBox.information(self, "已在列表", f"{p} 已在任务列表"); return
    self._add_project(p)
```

#### 删除（`[🗑 删除]`）

弹三项 QMessageBox：

```python
def _on_delete_clicked(self):
    p = self._selected_project()
    if p is None: return
    box = QMessageBox(self)
    box.setWindowTitle("删除项目")
    box.setText(f"确认删除「{p.name}」？")
    btn_listonly = box.addButton("仅从列表移除", QMessageBox.AcceptRole)
    btn_purge = box.addButton("连同目录删除", QMessageBox.DestructiveRole)
    box.addButton(QMessageBox.Cancel)
    box.exec()
    if box.clickedButton() is btn_listonly:
        self._remove_from_list(p)
    elif box.clickedButton() is btn_purge:
        if self._has_active_worker(p):       # 由 ScreenwriterPanel 注入回调
            QMessageBox.warning(self, "项目仍在生成", "请先停止当前阶段"); return
        shutil.rmtree(p, ignore_errors=False)
        self._remove_from_list(p)
```

### 3.5 自动剪枝

`refresh()` 时如果某 project 目录已不存在（用户手动删了文件夹），从 list 移除并 `cfg.update_settings(screenwriter_projects=[...])` 落盘。

### 3.6 刷新触发

- `ScreenwriterPanel.projectStateChanged` 信号（子面板 save / stream done / failed 时 emit） → `refresh()`
- `QTimer`（成员字段，`setInterval(30000)` + `start()`，repeating）定时刷新，捕获文件外部改动

---

## 4. 子面板改造：worker dict 化（破坏 T2/T3/T5/T6/T8）

### 4.1 `_BaseStagePage` 新字段

```python
self._project_dir: Path | None = None              # 当前显示
self._workers: dict[Path, StreamWorker] = {}       # 后台跑着的 worker
self._buf_by_project: dict[Path, str] = {}         # 流缓冲
self._state_by_project: dict[Path, str] = {}       # idle/streaming/done/error
self._error_by_project: dict[Path, str] = {}       # 失败消息
```

### 4.2 `_BaseStagePage` 新方法

- `is_streaming(project_dir: Path) -> bool` — 给 TaskManager 用
- `_active_worker() -> StreamWorker | None` — 当前 `_project_dir` 的 worker
- `_on_project_switched(old: Path|None, new: Path|None) -> None` — 子类可 override，默认 no-op

### 4.3 `set_project` 新语义（必须在子类调 `super().set_project()` 之前/之后规范）

```python
def set_project(self, path: Path | None):
    if self._project_dir and not self.try_release():
        return
    old = self._project_dir
    self._project_dir = path
    if path is None:
        self._render_empty(); return
    self._load_from_disk()
    if path in self._workers and self._workers[path].isRunning():
        self._enter_streaming_view(replay_buf=self._buf_by_project.get(path, ""))
    else:
        self._enter_idle_view()
    self._on_project_switched(old, path)
```

### 4.4 `StreamWorker` 签名改造（破坏 T2）

```python
class StreamWorker(QThread):
    event = Signal(str, dict, str)        # event_name, data, project_dir
    finished_ok = Signal(str)             # project_dir
    failed = Signal(str, str)             # msg, project_dir

    def __init__(self, client, path, body, params, project_dir, parent=None):
        ...
        self._project_dir = str(project_dir)

    def run(self):
        try:
            for ev in self._client.stream_post(self._path, self._body, params=self._params):
                if self.isInterruptionRequested(): return
                self.event.emit(ev.get("event", ""), ev.get("data", {}), self._project_dir)
            self.finished_ok.emit(self._project_dir)
        except Exception as e:
            self.failed.emit(str(e), self._project_dir)
```

### 4.5 SSE handler 模板

```python
def _on_sse_event(self, event_name: str, data: dict, project_dir_str: str):
    proj = Path(project_dir_str)
    if event_name == "delta":
        self._buf_by_project[proj] = self._buf_by_project.get(proj, "") + data.get("text", "")
    elif event_name == "done":
        # 落盘 / 解析（与当前 _project_dir 无关）
        self._handle_done(proj, data)
    elif event_name == "error":
        self._error_by_project[proj] = data.get("hint") or data.get("message", "")
    # 只有当前显示这个项目才更新 UI
    if proj != self._project_dir:
        return
    # ...更新 UI（在子类各自实现）
```

### 4.6 上游缺失 banner（issue #4 设计要求）

stage stepper 允许无脑跳到任意阶段。但子面板在 `set_project()` 之后，必须自检上游产物：

- `ScriptPage` 需要 `创意.json`
- `StoryboardPage` 需要 `剧本.md`
- `PromptsPage` 需要 `分镜.json`

缺失时：
- 显示灰色 banner「上游缺失：请先在『[阶段名]』生成或手动放入 `[文件名]`」
- 「生成」按钮 disabled
- 但本阶段已有产物（如直接放好的文件）→ 允许编辑 + 推进

每个子面板用一个 `QLabel`（statyleSheet `background:#3a3a2a; color:#9aa0a6; padding:6px;`）作为 banner，hide/show 切换。banner 单元统一放在主编辑器之上、紧接参数栏之下。

### 4.7 caller 更新

`IdeatePage._start_stream` / `ScriptPage._start_stream` / `StoryboardPage._start_stream` 都改：

```python
self._worker = StreamWorker(self._client, path, body, params,
                              project_dir=self._project_dir, parent=self)
self._workers[self._project_dir] = self._worker
self._worker.event.connect(self._on_sse_event)
self._worker.finished_ok.connect(self._on_stream_done_signal)
self._worker.failed.connect(self._on_stream_failed)
self._worker.start()
```

`_on_stream_done_signal(project_dir)` 和 `_on_stream_failed(msg, project_dir)` 都要更新签名。

---

## 5. 任务持久化

### 5.1 `AppSettings` 新字段

`drama_shot_master/core/app_settings.py`（或对应 dataclass）：

```python
screenwriter_projects: list[str] = field(default_factory=list)
# 绝对路径字符串数组；与 screenwriter_project_root 区分——后者只是「新建」按钮的默认 base
```

### 5.2 `ScreenwriterTaskManager` 持久化逻辑

```python
def __init__(self, cfg, parent=None):
    super().__init__(parent)
    self._cfg = cfg
    self._projects: list[Path] = [Path(p) for p in (cfg.screenwriter_projects or [])]
    self._build_ui()
    self.refresh()

def _add_project(self, p: Path):
    if p in self._projects: return
    self._projects.append(p)
    self._save()
    self.refresh()
    self.projectAdded.emit(p)

def _remove_from_list(self, p: Path):
    if p in self._projects:
        self._projects.remove(p)
        self._save()
        self.refresh()
        self.projectRemoved.emit(p)

def _save(self):
    self._cfg.update_settings(screenwriter_projects=[str(p) for p in self._projects])
```

---

## 6. 错误处理 + 边界

### 6.1 切走的 worker 后台 failed

- 不弹 QMessageBox（用户看不见）
- `_error_by_project[proj] = msg`
- emit `projectStateChanged` → TaskManager 行红色 `✗ [阶段名] 失败`
- 用户切回该项目 → page 在 `_load_from_disk()` 之后检测 `_error_by_project` → 由子面板**自己**渲染失败 banner（位置子面板自定，推荐贴近本面板的主编辑器顶部）；banner 文字「上次 [阶段名] 失败：[msg]，[重试 / 关闭]」，[关闭] 清掉 `_error_by_project[proj]`

### 6.2 删除时 worker 在跑

- 「连同目录删」拒绝（QMessageBox warning，要求用户先停）
- 「仅从列表移除」允许：worker 继续跑落盘，page dict 不 pop（避免 callback crash），但用户已看不到该项目

### 6.3 try_release 统一切换

```python
# ScreenwriterPanel._on_task_selected(new_path):
for page in self._pages:
    if not page.try_release():
        self._task_manager._restore_previous_selection()
        return
for page in self._pages:
    page.set_project(new_path)
```

### 6.4 项目目录被外部删

- `refresh()` 检测 `not p.is_dir()` → 自动剪枝（§5.2 `_remove_from_list`）
- 若当前选中项目被删 → emit `taskSelected(None)`，page 进入 empty 视图

### 6.5 worker 异常退出

QThread 崩溃后 dict entry 仍在。`set_project` 时检测 `worker.isRunning()` False → 清 dict 项，视为完成。

### 6.6 配置脏数据

`cfg.screenwriter_projects` 里 path 解析失败 → refresh 时跳过 + 日志 warning。

---

## 7. 测试矩阵

### 7.1 `ScreenwriterTaskManager`

`tests/test_ui/screenwriter/test_task_manager.py`：

- `test_refresh_empty_list_shows_no_rows`
- `test_refresh_renders_status_dots_from_files(tmp_path)`
- `test_refresh_prunes_missing_dirs(tmp_path)`
- `test_new_creates_subdir_under_root(tmp_path, monkeypatch)`
- `test_new_same_name_warns(tmp_path)`
- `test_open_adds_external_dir(tmp_path)`
- `test_open_duplicate_warns(tmp_path)`
- `test_delete_list_only_keeps_dir(tmp_path)`
- `test_delete_purge_removes_dir(tmp_path)`
- `test_delete_blocked_when_worker_active`
- `test_task_selected_emits_path`

### 7.2 `_BaseStagePage` worker-dict 化（修改 T3 测试）

`tests/test_ui/screenwriter/test_base_stage_page.py`：

- `test_active_worker_returns_none_when_empty`
- `test_is_streaming_reads_from_workers_dict(tmp_path)`
- `test_set_project_replays_buffer_when_switching_to_streaming_project(tmp_path)`

### 7.3 `StreamWorker` 三参签名（修改 T2 测试）

- 既有测试改传 `project_dir` 参数
- `test_event_signal_includes_project_dir`
- `test_finished_signal_includes_project_dir`
- `test_failed_signal_includes_project_dir`

### 7.4 子面板回归（T5 / T6 / T8 必须仍绿）+ 上游 banner

- 改 `_start_stream` 传 `project_dir`
- 改 `_on_sse_event` 签名
- 5 + 8 + 6 = 19 个既有测试要全绿
- **新增** `test_upstream_banner_shows_when_dep_missing`（ScriptPage/StoryboardPage/PromptsPage 各一个）：set_project 到一个没有上游文件的 tmp_path → upstream banner 可见、生成按钮 disabled

### 7.5 `ScreenwriterPanel` 装配

`tests/test_ui/screenwriter/test_screenwriter_panel.py`：

- `test_panel_builds_with_splitter_and_4_pages`
- `test_task_selection_propagates_to_all_pages(tmp_path)`
- `test_dirty_page_blocks_task_switch(tmp_path)`
- `test_stage_stepper_unconditional_switch`

### 7.6 集成

- `test_two_projects_streaming_concurrently_keeps_both_workers(tmp_path)` — 给 page 灌 2 个 mock worker (A, B 项目) → 切到 A 时只显示 A 的 UI，B 的 worker 仍 running

### 总数

- 新增 ~20
- 修改 ~5 既有

---

## 8. 与现有 wizard plan 的关系

- T7 子控件（`_ShotsTableModel` / `_CharacterRow` / `_WarningsBanner`）：无影响，保留
- T1 (`client.stream_post` 三参) ✅ 保留
- T2 (`StreamWorker`) 改：加 `project_dir` 参数
- T3 (`_BaseStagePage`) 改：加 worker dict 等字段
- T5 / T6 / T8 (子面板) 改：caller 适配新签名
- T9 / T10 (`_ProductTree` + `PromptsPage`) 待实现，按新签名实现
- T11 (`ScreenwriterPanel` 装配) 重写：装 splitter + TaskManager + WizardHost
- T12 (验收) 重写：覆盖任务栏化的端到端

---

## 9. 文件清单

### 新建

- `drama_shot_master/ui/widgets/screenwriter/task_manager.py` — ScreenwriterTaskManager
- `drama_shot_master/ui/widgets/screenwriter/wizard_host.py` — ScreenwriterWizardHost（stepper + stack）
- `tests/test_ui/screenwriter/test_task_manager.py`
- `tests/test_ui/screenwriter/test_screenwriter_panel.py`

### 修改

- `drama_shot_master/ui/widgets/screenwriter/stream_worker.py` — 三参签名
- `drama_shot_master/ui/widgets/screenwriter/base_stage_page.py` — worker dict 字段 + 新方法
- `drama_shot_master/ui/widgets/screenwriter/ideate_page.py` — caller 适配
- `drama_shot_master/ui/widgets/screenwriter/script_page.py` — caller 适配
- `drama_shot_master/ui/widgets/screenwriter/storyboard_page.py` — caller 适配
- `drama_shot_master/ui/panels/screenwriter_panel.py` — 完全重写，从 MVP 占位 → 任务栏化
- `drama_shot_master/core/app_settings.py`（或对应文件）— 加 `screenwriter_projects` 字段
- 对应既有测试 5 个文件 — 适配新签名

---

## 10. 验收标准

1. `tests/test_ui/screenwriter/` 全套件全绿（既有 + 新增）
2. 应用启动 → 编剧面板加载 → 左侧任务栏可见且空（首次）
3. 「+ 新建」可建项目目录，列表立即刷新
4. 「打开」可纳入外部目录
5. 「删除」可选「仅移除」或「连目录删」
6. 选中任务 → 右侧 wizard 切到该项目的 4 阶段 stack
7. stage stepper 可点切换任意阶段（无上游产物 → 子面板自己显示「上游缺失」banner）
8. 启动项目 A 的剧本流式生成，切到项目 B 点分镜流式生成 → 两个 worker 同时跑、两行状态点都显示 `●`
9. 切回项目 A → 剧本编辑器显示 A 的实时流（buffer replay）
10. 项目 A 流式中点删除 → 弹三项 dialog，「连目录删」被拒绝并提示
