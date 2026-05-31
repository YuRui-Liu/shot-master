# [2.剧本] 左右分栏（主从）布局重构 — 设计稿

**日期:** 2026-05-30
**文件:** `drama_shot_master/ui/widgets/screenwriter/script_page.py`

## 目标（一句话）

把「大纲（集列表）」与「剧集（选中集脚本）」在**视觉**与**数据**上彻底分开，
消除多集模式下大纲流式文本灌进剧集编辑器、且两块挤在一条竖排里的混淆。

## 问题现状

`ScriptPage._build_ui` 当前是单条 `QVBoxLayout`：
参数栏 → 上游横幅 → `_outline_table`(maxHeight 200) → 一键全集 bar → `_episode_editor` → 操作栏。

两个缺陷：
1. **空间混淆**：大纲表与剧集编辑器同屏竖排，分不清。
2. **数据混淆**：`_on_sse_event` 的 `delta` 把大纲流式文本也写进 `_episode_editor`
   （`ep_id == self._current_episode` 在大纲流时常成立），与剧集脚本共用一个编辑器。

## 选定方案：A · 左右分栏（主从）

左＝大纲集列表导航，右＝剧集正文编辑。脚本类工具最常见形态，分离最彻底。
已确认两个细节：
- **大纲流式去向**：左栏临时只读预览，解析完成后变回集列表。
- **左栏宽度**：`QSplitter` 可拖拽 + 一键折叠。

## 架构

### 布局（`_build_ui` 重构）

```
QVBoxLayout(root):
  ├─ _build_param_bar()              # 整宽，不变：集数/时长/语言风格/生成/中止/状态
  ├─ _upstream_banner               # 整宽，不变
  ├─ QSplitter(Qt.Horizontal)  ← self._splitter
  │    ├─ 左栏 QWidget (self._left_pane):
  │    │     QVBoxLayout:
  │    │       header: QLabel("大纲 · 集列表")            # 折叠按钮在右栏表头，见下
  │    │       _outline_table  (去掉 setMaximumHeight，stretch=1)
  │    │       _outline_preview (QPlainTextEdit, 只读, 默认 hide, stretch=1)
  │    │       batch bar: _batch_btn + _batch_progress
  │    └─ 右栏 QWidget (self._right_pane):
  │          QVBoxLayout:
  │            header row: [_collapse_btn("◀ 大纲")] + QLabel(self._episode_title_lbl "剧集 · 正文")
  │            _episode_editor (stretch=1)
  └─ _build_action_bar()             # 整宽，不变：保存/打开/推进
```

- `QSplitter` 默认尺寸比例约 `[32, 68]`，`setCollapsible(0, True)`。
- **折叠按钮** `_collapse_btn` 放右栏表头（始终可见）：
  - 展开态文案「◀ 大纲」，点击 → 记住 `self._splitter.sizes()` 到 `self._saved_sizes`，
    `setSizes([0, total])`，文案变「▶ 大纲」。
  - 折叠态点击 → 恢复 `self._saved_sizes`，文案变回「◀ 大纲」。
- **控件同名保留**：`_outline_table` / `_episode_editor` / `_batch_btn` / `_batch_progress`
  / `_gen_btn` / `_stop_btn` / `_save_btn` / `_open_btn` / `_advance_btn` / `_upstream_banner`
  / `_stream_label` 全部保留原属性名（仅父容器变化），保证既有 11 项测试不破。

### 数据流（根治混淆）

新增：`self._outline_preview`（左栏只读编辑器，默认 hide）、`self._outline_streaming: bool = False`。

1. `_start_outline_stream`：
   - `self._outline_streaming = True`
   - 左栏：`_outline_table.hide()`；`_outline_preview.clear(); _outline_preview.show()`
   - 其余（worker 启动等）不变。
2. `_on_sse_event` 的 `delta` 分支：
   ```
   if self._outline_streaming:
       self._outline_preview.moveCursor(End); insertPlainText(text)   # 进左栏预览
   else:
       <原逻辑：进 _episode_editor（剧集流式）>
   ```
   → 大纲文本不再进剧集编辑器。
3. `done` 分支：
   - `saved.endswith("剧本.json")`（大纲完成）→
     `self._outline_streaming = False`；`_outline_preview.hide(); _outline_table.show()`；
     `self._load_index()`（原有）。
   - episode 完成分支不变（含上一轮修的单集快路径 `rowCount()==0 → _load_index()`）。
4. `error` 分支：若 `self._outline_streaming` → 复位
   （`_outline_streaming=False`，`_outline_preview.hide(); _outline_table.show()`），再走原报错。
5. `_stop_stream`：若正处于大纲流，同样复位预览视图。

右栏 `_episode_title_lbl` 在选集 / episode done 时更新为「剧集 · {ep} 正文」。

## 错误处理

- 大纲流式中途失败 / 中止：复位为列表视图，不残留预览态。
- 折叠态下生成大纲：预览仍渲染在（宽度 0 的）左栏；建议生成大纲时若左栏折叠则自动展开
  （`_start_outline_stream` 内：若 `_splitter.sizes()[0] == 0` 则恢复默认比例）。

## 测试

新增（`tests/test_ui/screenwriter/test_script_page.py`，offscreen Qt）：
1. `test_outline_delta_goes_to_preview_not_editor`：置 `_outline_streaming` 态后发 `delta`，
   断言 `_outline_preview` 含文本且 `_episode_editor` 为空。
2. `test_outline_done_restores_list_view`：大纲 `done`(saved=剧本.json) 后
   断言 `_outline_preview.isHidden()` 且 `_outline_table.isVisible()` 且列表已渲染。
3. `test_collapse_toggle_hides_left_pane`：点 `_collapse_btn` → `_splitter.sizes()[0]==0`；
   再点 → 恢复 >0。
4. `test_episode_select_loads_right_editor`：渲染多集后选第 2 行 → `_episode_editor` 载入该集。

回归：既有 11 项 script_page 测试 + 单集快路径测试须全绿。

## 非目标（YAGNI）

- 不改 agent 端 `/script/outline`、`/script/episode` 契约。
- 不持久化折叠状态（仅会话内）。
- 不改大纲表的列结构（集/标题/概要/操作 沿用）。
- 不动其它阶段页。
