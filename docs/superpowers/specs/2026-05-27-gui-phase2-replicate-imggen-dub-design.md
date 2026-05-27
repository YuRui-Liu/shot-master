# Phase 2 replicate：图片生成 + 配音 改主-详+浮出 设计

- 日期：2026-05-27
- 关系：复制 Phase 2 视频试点已验证的 `TaskWorkspacePage` + `DetachedEditorWindow` 模式
  （见 [`2026-05-27-gui-phase2-master-detail-design.md`](2026-05-27-gui-phase2-master-detail-design.md)）到「图片生成」「配音」。
- 范围：**仅 imggen + dub**。配乐因需重构（从 321 行 `SoundtrackTaskWindow` 抽出 `SoundtrackEditor` + 适配 dict 模型）**单独成下一个 spec/plan**，本期不动。

---

## 1. 目标与不变量

把图片生成、配音从「任务列表 + 双击开窗」改为窗内主-详 + 浮出独立窗，复用 Phase 2 的通用组件。
**通用机制不改**：`TaskWorkspacePage`（每任务缓存编辑器 + 浮出 reparent + flush_all + discard_editor +
update_task_name）与 `DetachedEditorWindow`（承载浮出编辑器、关窗收回、reparent 后 `editor.show()` 防空白）保持现状。

**不变**：算法/provider/数据模型/stores/config 持久化；**soundtrack 行为完全不动**（仍双击开窗，下个 plan 处理）；视频已完成不回改。

## 2. 各功能适配器（注入 TaskWorkspacePage，与视频同形）

两功能的编辑器接口与视频不同（视频 `submitStarted/Done/Failed` + `model.to_dict()`；这两类
`statusChanged(str)/resultReady(str)/dirty()` + `to_payload()`）。每功能由 AppShell 的
`_make_<fn>_page` 注入：

| 注入点 | 图片生成(imggen) | 配音(dub) |
|---|---|---|
| `editor_factory(task)` | `ImgGenPanel(self.cfg, payload=task.payload)` | `DubPanel(self.cfg, payload=task.payload)` |
| `wire_editor(ed, task)` | 见下 | 见下 |
| `payload_of(ed)` | `ed.to_payload()` | `ed.to_payload()` |
| `on_persist(tid, payload)` | `self._on_imggen_dirty` | `self._on_dub_dirty` |
| `title_for(task)` | `f"图片生成 · {task.name}"` | `f"配音 · {task.name}"` |
| 浮出窗尺寸 | **(720, 780)** | (1100, 820) |

`wire_editor(ed, task)`（tid=task.id）统一接三类信号 + 保留"每次编辑即落盘"（这两类有 `dirty`，视频没有）：
```python
ed.statusChanged.connect(lambda s: self._on_<fn>_status(tid, s))
ed.resultReady.connect(lambda p: self._on_<fn>_result(tid, p))
ed.dirty.connect(lambda: self._on_<fn>_dirty(tid, ed.to_payload()))
```
TaskWorkspacePage 的 switch/pop/flush 持久化（`payload_of`+`on_persist`）是额外安全网，与 `dirty` 即时落盘并存、无害。

## 3. 管理面板改造（imggen + dub，各自逐个适配内部名）

两面板与 `VideoTaskManagerPanel` 同构但内部命名/机制不同：
- `ImgGenTaskManagerPanel`/`DubTaskManagerPanel`：cb 存为 `self._open_cb`/`self._close_cb`/`self._persist`；
  选中取 `self._selected_id()`；槽名 `_new`/`_open`/`_dup`/`_del`/`_rename`；**refresh 用 `self._loading` 标志而非 `blockSignals`**；
  imggen 用 `QInputDialog` 取名新建。`taskRenamed` 已存在。

每面板改动（仅这两个文件）：
1. 加信号 `taskSelected = Signal(object)` 与 `taskDeleted = Signal(str)`。
2. `_build_ui` 连 `self.table.itemSelectionChanged.connect(self._on_selection_changed)`；新增：
   ```python
   def _on_selection_changed(self):
       if self._loading:            # refresh 期间不误发
           return
       tid = self._selected_id()
       if not tid:
           return
       t = self.store.get(tid)
       if t is not None:
           self.taskSelected.emit(t)
   ```
   （`_loading` 守卫是关键：这两面板 refresh 不用 blockSignals，否则会在重建表时误发选择。）
3. 移除「打开」按钮（从按钮 bar 去掉）与其槽 `_open`；移除 `self.table.doubleClicked.connect(self._on_double)`
   与 `_on_double` 里的 `self._open()` 调用（col-0 内联改名走表的 DoubleClicked 编辑触发，不受影响——保留）。
4. `_new`：建任务后不再 `self._open_cb(t)`，改为选中新行（触发 taskSelected）。新增 `_select_task(task_id)`：
   ```python
   def _select_task(self, task_id):
       for r in range(self.table.rowCount()):
           it = self.table.item(r, 0)
           if it and it.data(Qt.UserRole) == task_id:
               self.table.setCurrentCell(r, 0)   # QTableWidget 无 setCurrentRow
               break
   ```
5. `_del`：删成功后 `self.taskDeleted.emit(tid)`；移除 `self._close_cb(tid)` 调用。
6. 构造签名保留 `open_window_cb, close_window_cb` 形参（AppShell 传 None，不再调用），减少改动面。

## 4. DetachedEditorWindow：尺寸参数化

`DetachedEditorWindow.__init__` 加可选 `size: tuple[int,int] = (1100, 820)`，用 `self.resize(*size)`；
图片页传 `(720, 780)`。其余（reparent 后 `editor.show()` 防空白、closed 信号、深色标题栏+图标）不变，三类共享。

## 5. AppShell 接入（imggen + dub 各自原子切换）

- `_build_pages`：`"imggen"` 与 `"dubbing"` 的构造从 `_make_imggen_panel`/`_make_dub_panel`（返回裸 manager）
  改为 `_make_imggen_page`/`_make_dub_page`（返回 `TaskWorkspacePage`）。移除 `self._open_imggen_windows`/`self._open_dub_windows`。
- 新增 `_make_imggen_page`/`_make_dub_page`（结构同 `_make_video_page`）：建对应 manager（cb 传 None）+
  `editor_factory`/`wire_editor`/`payload_of`/`on_persist`/`title_for` + 浮出尺寸；连 `manager.taskRenamed→_on_<fn>_renamed`、`manager.taskDeleted→page.discard_editor`。
- 删除：`_open_imggen_window`/`_close_imggen_window`/`_on_imggen_window_closed`、
  `_open_dub_window`/`_close_dub_window`/`_on_dub_window_closed`。
  **保留** `_on_imggen_status/_result/_dirty/_persist_imggen_tasks/_on_imggen_renamed` 与 dub 对应（page/wire 仍用）。
- `_imggen_manager()`/`_dub_manager()` → 返回 `self.pages["imggen"].manager` / `["dubbing"].manager`。
- `_on_imggen_renamed`/`_on_dub_renamed` → 改为 `self.pages[key].update_task_name(task_id, name)`（同步内嵌头+浮出窗标题）。
- `_wire`：删除 `self._dub_manager().taskRenamed.connect(...)` 那行（改在 `_make_dub_page` 内连）；statusMessage 循环已对 `TaskWorkspacePage` 走 `page.manager.statusMessage`（视频期已实现，无需改）。
- `closeEvent`：imggen/dub 段从遍历 `_open_*_windows` 落盘改为 `self.pages[key].flush_all()`。
- DetachedEditorWindow 浮出窗的 task 重命名标题同步由 page.update_task_name 内部处理（与视频一致）。

切换确认（grep 应为空）：`_open_imggen_window|_close_imggen_window|_on_imggen_window_closed|_open_imggen_windows|_open_dub_window|_close_dub_window|_on_dub_window_closed|_open_dub_windows|ImgGenTaskWindow|DubTaskWindow`（app_shell.py 内）。

## 6. 退役旧窗
删除 `drama_shot_master/ui/windows/imggen_task_window.py` 与 `drama_shot_master/ui/windows/dub_task_window.py`，
清理引用（预期仅其自身/可能的旧测试）。

## 7. DRY 取舍（已确认）
video/imggen/dub 三个 `_make_*_page` 高度同形，但信号名/payload/ctor/窗尺寸差异真实，且重构已上线的
`_make_video_page` 有风险。**本期保持三个显式 `_make_*_page`，不抽公共适配器**；若配乐令其成第 4 个再评估。

## 8. 测试（headless offscreen smoke）
- 新 `tests/test_ui/test_imggen_workspace_smoke.py` / `test_dub_workspace_smoke.py`：
  AppShell 的 `imggen`/`dubbing` 页是 `TaskWorkspacePage`；`_imggen_manager()/_dub_manager()` 返回 page.manager；
  manager 选中行发 `taskSelected`、删除发 `taskDeleted`；选中任务建对应 `ImgGenPanel`/`DubPanel` 编辑器（在 `page._editors`）。
- 各 manager 单测：`taskSelected` 在 refresh(`_loading`) 期间不误发；`_new` 后选中新行。
- app_shell smoke：补 imggen/dub 页类型断言。
- 通用 page/detached 已有测试覆盖 reparent/pop-out/可见性，不重复。
- 验收：`grep -r qfluentwidgets` 为空；`python -m pytest tests/` 全绿；真机点开图片/配音页验主-详+浮出（图片窗较小）。

## 9. 非目标（YAGNI）
- 配乐（soundtrack）—— 下一个 spec/plan（含 SoundtrackEditor 抽取 + dict 模型适配 + try-import）。
- 不抽公共 `_make_*_page` 适配器（§7）。
- 不改编辑器内部 UI / 不改 SoundtrackPanel / 不改通用 TaskWorkspacePage 行为。

## 10. 风险
- **imggen/dub manager 选择信号在 refresh 误发**：必须用 `self._loading` 守卫（§3.2）。读代码确认 refresh 起止处置 `_loading=True/False`。
- **`store.get`**：确认 ImgGen/Dub store 有 `get(tid)`（视频 store 有；这两 store 同族应同样有——读代码确认，否则用 `next(t for t in store.all() if t.id==tid)`）。
- **`_new` 的 QInputDialog**：headless 测试不能弹真实对话框 → 测试直接调 `store.add` + `_select_task`，或对 `_new` 不做 UI 断言（只测选择/taskSelected 路径）。
- **删窗引用**：删除前 grep 确认无生产代码引用 ImgGen/DubTaskWindow。
