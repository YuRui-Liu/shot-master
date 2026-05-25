# 多任务并行视频生成（独立任务窗口）设计

**项目**：drama-shot-master
**版本**：v0.7.x 增量（设计阶段）
**日期**：2026-05-25
**状态**：设计评审通过，待写实现 plan
**关联**：重构现有单实例 `VideoPanel`（`video_panel.py`）+ 单缓存 `cfg.video_timeline_cache` 为多任务体系。

---

## 1. 背景与目标

### 1.1 问题

视频生成单条耗时 4–10 分钟。当前只有一个 `VideoPanel`（嵌在主窗 stack）+ 一份 `video_timeline_cache`，一次只能编辑/提交一个任务。用户想并行跑多个，并能在某个结果不满意时回到对应任务重新生成，而不必重拖轨道、重写提示词。

### 1.2 目标

- 「视频生成」主页变成**任务管理列表**；每个任务可在**独立顶级窗口**打开。
- 多个任务窗口可同时开着、各自提交、并行执行、并行监控进度。
- 任务的轨道/提示词等**持久化**；关窗或关 app 后可重新打开、重新生成。

### 1.3 非目标

- 跨 app 重启**续跑轮询**（只持久化状态，不重新附着在途任务）
- 关窗强制确认/阻塞
- 并行上限 / 队列调度
- 任务间拖拽复制段（用「复制任务」整体克隆替代）
- 云端任务历史拉取

---

## 2. 关键决策（评审 Q&A）

| 决策点 | 选择 | 理由 |
|---|---|---|
| 多任务形态 | 独立顶级窗口（每任务一个 QMainWindow） | 契合"多个任务窗口"+并行监控 |
| 管理方式 | 「视频生成」区变任务管理列表（新建/打开/复制/删除） | 随时找回任务 |
| 进行中关窗 | 状态持久化，进度只在内存；关窗停本地轮询（云端可能仍跑），重开重提 | 契合"重新点生成"；避免续跑复杂度 |
| 编辑器复用 | 现有 VideoPanel 参数化（接收外部 model），移进独立窗口 | 不重写编辑器 |
| 并发 | 无上限（受 RunningHub 账户约束） | YAGNI |

---

## 3. 架构

| 单元 | 文件 | 职责 |
|---|---|---|
| 任务数据 + store | `core/video_task_store.py`（新增，Qt-free） | `VideoTask` dataclass + `VideoTaskStore` 列表增删改查 + 序列化 |
| config 字段 + 迁移 | `config.py`（改） | `video_tasks` 落盘 + 旧 `video_timeline_cache` 迁移 |
| 任务管理面板 | `ui/panels/video_task_manager_panel.py`（新增） | 列表 + 新建/打开/复制/删除；调 `open_task_window` 回调 |
| 独立任务窗口 | `ui/windows/video_task_window.py`（新增） | 顶级窗，内嵌参数化 VideoPanel + 自己的提交 worker；发状态信号 |
| 编辑器参数化 | `ui/panels/video_panel.py`（改） | 构造接收 `model` + `on_change`，移除单缓存读写 |
| 主窗接线 | `ui/main_window.py`（改） | stack 第 5 槽换成 manager；实现 `open_task_window`；closeEvent 存所有窗 |

边界：`video_task_store` 无 Qt 依赖、可单测；manager 与 window 通过回调 + 信号通信；VideoPanel 仅依赖传入的 model。

---

## 4. 详细设计

### 4.1 `core/video_task_store.py`

```python
from dataclasses import dataclass, field
import time
from secrets import token_hex

def _gen_task_id() -> str:
    return f"{int(time.time() * 1000)}{token_hex(3)[:5]}"

@dataclass
class VideoTask:
    id: str
    name: str
    timeline: dict                  # TimelineModel.to_dict()
    updated_at: float = 0.0         # epoch 秒
    last_result: str = ""           # 上次成功的 mp4 路径

    def to_dict(self) -> dict: ...          # 全字段
    @classmethod
    def from_dict(cls, d: dict) -> "VideoTask": ...   # 缺字段给默认


class VideoTaskStore:
    """内存维护任务列表；调用方负责落盘（store.to_list() → cfg.update_settings）。"""
    def __init__(self, tasks: list[VideoTask] | None = None):
        self._tasks = list(tasks or [])

    def all(self) -> list[VideoTask]: ...
    def get(self, task_id: str) -> VideoTask | None: ...
    def add(self, name: str, timeline: dict) -> VideoTask:   # 生成 id+updated_at，追加
    def update(self, task_id, *, name=None, timeline=None, last_result=None) -> None:  # 改字段+刷 updated_at
    def remove(self, task_id: str) -> None: ...
    def duplicate(self, task_id: str) -> VideoTask:          # 深拷 timeline，name+" 副本"
    def to_list(self) -> list[dict]: ...
    @classmethod
    def from_list(cls, data: list[dict]) -> "VideoTaskStore": ...
```

### 4.2 config.py 字段 + 迁移

- 新增 `video_tasks: list[dict] = field(default_factory=list)`。
- `update_settings` 落盘 dict 增 `"video_tasks": self.video_tasks`。
- `load_config`：读 `video_tasks`（list 校验）。**迁移**：读完后若 `cfg.video_tasks` 为空且 `cfg.video_timeline_cache` 非空 →
  ```python
  cfg.video_tasks = [{
      "id": _gen_task_id(), "name": "默认任务",
      "timeline": cfg.video_timeline_cache,
      "updated_at": time.time(), "last_result": "",
  }]
  ```
  （`video_timeline_cache` 字段保留，不删；迁移只读它一次。`config.py` 为此 `import time` 并 `from drama_shot_master.core.video_task_store import _gen_task_id`——无循环依赖，store 不 import config。）

### 4.3 VideoPanel 参数化（`video_panel.py`）

当前：`__init__(self, state, cfg, parent=None)` → `self.model = self._restore_model()`；`save_cache()` 写 `cfg.video_timeline_cache`。

改为：
```python
def __init__(self, state, cfg, model: TimelineModel, on_change=None, parent=None):
    super().__init__(state, cfg, parent)
    self.model = model
    self._on_change = on_change          # 可选回调：编辑后通知 window 去抖存
    ...
```
- 删除 `_restore_model` / `save_cache`。
- 在所有改 model 的 slot 末尾（如 `_on_segment_edited`/`_on_global_changed`/增删段/audio）调 `self._notify_change()`：
  ```python
  def _notify_change(self):
      if self._on_change:
          self._on_change()
  ```
  （集中加在现有刷新点；不改信号契约。）
- 提交链路逻辑**保持不变**，仍用 `self._worker` / `self._cancel_flag` / `video_status_bar`。仅**新增 3 个转发信号** `submitStarted()` / `submitDone(str)` / `submitFailed(str)`，在现有 `_on_submit`（起 worker 时）/ `_on_submit_done` / `_on_submit_failed` 末尾各 emit 一次，供 window 转发给 manager（§4.4）。

> 注：BasePanel 仍是父类，但 VideoPanel 不再作为 stack 直接面板；它被 window 内嵌。`select_mode/validate/execute` 保留（window 不用主窗的执行按钮，submit 在面板内部按钮）。

### 4.4 `ui/windows/video_task_window.py`

```python
class VideoTaskWindow(QMainWindow):
    statusChanged = Signal(str, str)     # (task_id, status_text)
    resultReady = Signal(str, str)       # (task_id, mp4_path)
    timelineDirty = Signal(str, dict)    # (task_id, timeline_dict) 去抖后发

    def __init__(self, task: VideoTask, state, cfg, parent=None):
        ...
        self.model = TimelineModel.from_dict(task.timeline)
        self.editor = VideoPanel(state, cfg, self.model,
                                 on_change=self._on_dirty)
        self.setCentralWidget(self.editor)
        self.setWindowTitle(f"视频任务 · {task.name}")
        # 去抖 timer：on_change → 500ms 后 emit timelineDirty(task_id, model.to_dict())
        # 接 editor 的 submit 状态：通过 editor.video_status_bar 或转发
```
- **状态转发**：让 manager 知道生成中/完成/失败。最简单：window 监听 editor 内部提交状态。当前 `VideoPanel._on_submit/_on_submit_done/_on_submit_failed` 直接更新 `video_status_bar`。为让 window 拿到，给 VideoPanel 加 3 个转发信号 `submitStarted()` / `submitDone(str mp4)` / `submitFailed(str)`，在对应 slot 里 emit；window 接它们 → emit `statusChanged`/`resultReady`。
- **关窗**（`closeEvent`）：
  - emit 最新 `timelineDirty`（确保存盘）
  - 若 `editor._worker` 在跑：置 `editor._cancel_flag["v"]=True`（停本地轮询），断开 editor 的 submit 转发信号避免 use-after-free
  - 不弹阻塞确认

### 4.5 `ui/panels/video_task_manager_panel.py`

```python
class VideoTaskManagerPanel(BasePanel):
    def __init__(self, state, cfg, store: VideoTaskStore,
                 open_window_cb, persist_cb, parent=None):
        # open_window_cb(task) → main_window 开窗
        # persist_cb() → main_window 把 store.to_list() 落盘
```
- 一个 `QTableWidget`/`QListWidget`：列 = 名称 / 状态 / 上次结果 / 更新时间
- 按钮：`+ 新建任务`（add 空 timeline → 开窗）/ `打开`（选中行 → open_window_cb）/ `复制`（store.duplicate → 刷新）/ `删除`（确认 → store.remove + persist）/ `打开结果文件夹`
- 双击行 = 打开；重命名（双击名 cell → store.update(name) + persist + 若窗开着同步标题）
- 公共方法 `refresh()` 重画列表；`set_task_status(task_id, status)` 更新某行状态徽标
- BasePanel 接口：`select_mode()="none"`；`validate()=(False,"用列表内按钮")`；`execute()` raise（主窗对 video_gen 已隐藏执行按钮）

### 4.6 main_window 接线

- 构造 `self.video_store = VideoTaskStore.from_list(self.cfg.video_tasks)`
- stack 第 5 槽：`VideoTaskManagerPanel(state, cfg, self.video_store, self._open_task_window, self._persist_tasks)`
- `self._open_windows: dict[str, VideoTaskWindow] = {}`
- `_open_task_window(task)`：已开则 `raise_()`+`activateWindow()`；否则 new `VideoTaskWindow`，连：
  - `timelineDirty` → `store.update(timeline=...)` + `_persist_tasks()`
  - `statusChanged` → `manager.set_task_status(...)`
  - `resultReady` → `store.update(last_result=mp4)` + `_persist_tasks()` + manager 刷新
  - window `destroyed`/closeEvent → 从 `_open_windows` 移除
  - `window.show()`
- `_persist_tasks()`：`cfg.update_settings(video_tasks=self.video_store.to_list())`
- `closeEvent`：遍历 `_open_windows` 让各 window 存一次 timeline → `_persist_tasks()`；再 super

---

## 5. 数据流

```
[管理面板 + 新建任务] → store.add("任务 N", 空timeline) → open_window_cb(task)
[打开] → 已开?聚焦 : new VideoTaskWindow(task) → show
[窗口内编辑] → VideoPanel.on_change → 去抖 → timelineDirty → store.update + 落盘
[窗口内提交] → 自己的 worker（独立并行）→ submitStarted/Done/Failed
        → window.statusChanged/resultReady → 管理列表实时刷新 + last_result 落盘
[关窗/关app] → 停本地轮询(若在跑) + 存 timeline；状态回"空闲/上次结果"
[重开任务] → 从 store 恢复 timeline → 编辑/重新提交
```

---

## 6. 错误处理 / 生命周期

| 场景 | 行为 |
|---|---|
| 删除任务时其窗开着 | 先关窗（停轮询）再 remove |
| 打开已开任务 | 聚焦现有窗，不重复开 |
| 进行中关窗 | 置 cancel flag 停本地轮询；断开转发信号；存 timeline；无阻塞 |
| 提交失败 | window 内 status 显示失败（现有逻辑）；manager 行标"失败" |
| 旧单缓存存在、无 video_tasks | 迁移成一个"默认任务" |
| 后台 worker 回调命中已关窗口 | closeEvent 先断开 submit 转发信号 + QTimer 回调用存活判断，避免 use-after-free |

---

## 7. 测试

### 7.1 `tests/test_core/test_video_task_store.py`（TDD）

| 用例 | 验证 |
|---|---|
| add_appends_with_id | add 后 all() 含新任务、id 非空、updated_at>0 |
| get_by_id | get 命中/未命中(None) |
| update_fields | update name/timeline/last_result 生效 + updated_at 刷新 |
| remove | remove 后 get 为 None |
| duplicate_deep_copies | duplicate 后改原 timeline 不影响副本；name 带"副本" |
| roundtrip_to_from_list | to_list→from_list 还原全字段 |

### 7.2 `tests/test_config.py` 扩展

| 用例 | 验证 |
|---|---|
| video_tasks_roundtrip | update_settings(video_tasks=[…]) → reload 读回 |
| migrate_old_cache | settings.json 有 video_timeline_cache、无 video_tasks → load 后 video_tasks 含 1 个"默认任务"，timeline == 旧缓存 |
| no_migration_when_tasks_exist | 同时有两者 → 不迁移（video_tasks 原样） |

### 7.3 手测清单

1. 启动 → 「视频生成」显示任务管理列表（旧缓存已迁成"默认任务"）。
2. 新建任务 → 弹独立窗口；拖图、写 prompt；列表出现该任务。
3. 再新建一个任务 → 第二个独立窗口；两窗并存。
4. 两个窗口各点提交 → 两个 worker 并行跑；两窗状态栏各自进度；管理列表两行都显"生成中"。
5. 一个完成 → 该窗显示结果、管理列表该行显"完成 + mp4"。
6. 关掉一个窗 → 列表该行回"空闲/上次结果"；重开 → 轨道/prompt 原样恢复，可再提交。
7. 复制任务 → 新行，timeline 克隆，可独立改。
8. 删除任务（含其窗开着）→ 窗关、行消失。
9. 重启 app → 任务列表与各任务 timeline 持久化恢复。

---

## 8. 影响面

- 新增 3 文件（store / manager / window）+ 2 测试；改 config / video_panel / main_window
- 零新增 pip 依赖
- 兼容：旧 `video_timeline_cache` 自动迁移；不删旧字段
- 风险点：VideoPanel 参数化改造 + 后台 worker 跨窗生命周期（§6 末行已列处理）

---

## 9. 不做的事（YAGNI 清单）

- ❌ 跨重启续跑轮询
- ❌ 关窗强制确认
- ❌ 并行上限 / 队列
- ❌ 任务间拖段
- ❌ 云端历史拉取
- ❌ 任务分组/标签/搜索（列表够用）
