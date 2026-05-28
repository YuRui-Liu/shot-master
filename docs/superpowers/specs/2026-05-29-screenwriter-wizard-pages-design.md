# 编剧 Wizard 4 阶段子面板·设计稿

- 日期：2026-05-29
- 代号：`screenwriter_wizard_pages`
- 版本：v0.1.0（设计稿）
- 状态：待用户复审
- 上游 spec：[`2026-05-28-screenwriter-agent-design.md`](2026-05-28-screenwriter-agent-design.md)、[`2026-05-28-screenwriter-agent-mvp.md`（plan）](../plans/2026-05-28-screenwriter-agent-mvp.md)

---

## 0. 摘要

screenwriter agent MVP 已完成（后端 4 个 SSE endpoint 跑通、e2e mock LLM 链路绿）；主软件侧 `ScreenwriterPanel` 已有项目列表 master + 4 阶段标签头 detail，但 wizard 的 4 个子面板**都是 QLabel + QPlainTextEdit + 两按钮的占位**。本期把它们做成产品级 UI：每个阶段都有专属交互（聊天/编辑器/表格/产物树），接 SSE 流，支持中止/重生确认/外部编辑兼容。

---

## 1. 总体架构

### 1.1 面板结构

```
ScreenwriterPanel (QSplitter Horizontal — 既有，不动)
├── master（项目列表 + 按钮，既有，不动）
└── detail（既有外壳；wizard 占位重写）
    ├── 项目名 QLabel               既有
    ├── 阶段标签头（QButtonGroup exclusive）  既有
    └── QStackedWidget（4 个真实子面板）  ←  本期重做
        ├── IdeatePage         左候选 + 右聊天
        ├── ScriptPage         上参数 + 下编辑器
        ├── StoryboardPage     头部全局 + 镜头表格
        └── PromptsPage        左产物树 + 右预览
```

### 1.2 新增文件结构

```
drama_shot_master/ui/widgets/screenwriter/
├── __init__.py
├── stream_worker.py             QThread 包装 client.stream_post，event 信号转出主线程
├── ideate_page.py               IdeatePage 主类
├── _ideate_candidate_card.py    单个候选卡片
├── _ideate_message_bubble.py    单条聊天气泡
├── script_page.py               ScriptPage 主类（不再拆子 widget）
├── storyboard_page.py           StoryboardPage 主类
├── _shots_table_model.py        QAbstractTableModel 包装 _sb["shots"]
├── _character_row.py            角色单行（name + appearance + [×]）
├── _warnings_banner.py          自适应红条 + 行号跳转
├── prompts_page.py              PromptsPage 主类
└── _product_tree.py             QTreeWidget 包装：预期文件占位 + 状态点
```

修改既有：
- `drama_shot_master/ui/panels/screenwriter_panel.py`：删 wizard 占位，装配 4 个真实子面板，加 dirty 切换护栏
- `drama_shot_master/agents/screenwriter_client.py`：`stream_post` 加可选 `params` 参数（透传 query string）

### 1.3 关键架构决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 流式接入 | 每子面板用 StreamWorker(QThread) wrap stream_post | 不堵 UI 主线程；中止 = `requestInterruption()` + httpx 自动断开 |
| 单次用完即抛 | 每次生成新建 StreamWorker，不复用 | 避免状态污染 |
| 单一真相源 | 产物落盘后 UI 重读文件刷新，**不在 UI 维护双副本** | 外部编辑兼容；mtime 检测+提示重载 |
| 状态机驱动 | 每子面板内部 `_state ∈ {idle, streaming, done, error}` 统一驱动按钮可用性 | 不会出现"流式中可以再点生成"等错乱 |
| 重生策略 | done 状态点[生成] → 弹覆盖确认 → `?purge_downstream=true` | 与 Agent spec §3.10 对齐；下游过期不混乱 |
| dirty 切换护栏 | 切阶段/切项目时调当前页 `try_release() -> bool` | 复用既有 TaskWorkspacePage flush 模式；False 则阻断切换 |
| 未选项目时 | 子面板整体显占位屏（按钮全禁），子控件不构建 | 简化空状态；切到有项目时一次性 build |

---

## 2. 公共基础设施：StreamWorker

**文件：** `drama_shot_master/ui/widgets/screenwriter/stream_worker.py`

```python
"""SSE 流式 worker：阻塞迭代器 → Qt 信号流，避免堵 UI 线程。"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class StreamWorker(QThread):
    """单次用完即抛；每次生成新建一个。"""
    event = Signal(str, dict)       # (event_name, data_dict)
    finished_ok = Signal()          # 流自然结束
    failed = Signal(str)            # 异常（网络/解析）

    def __init__(self, client, path: str, body: dict,
                 params: dict | None = None, parent=None):
        super().__init__(parent)
        self._client = client
        self._path = path
        self._body = body
        self._params = params or {}

    def run(self):
        try:
            for ev in self._client.stream_post(self._path, self._body,
                                                params=self._params):
                if self.isInterruptionRequested():
                    return                # httpx context manager 自动 close 流
                self.event.emit(ev.get("event", ""), ev.get("data", {}))
            self.finished_ok.emit()
        except Exception as e:
            self.failed.emit(str(e))

    def stop(self):
        """主线程槽里调；线程检测到 interruption flag 后退循环。"""
        self.requestInterruption()
```

**子面板统一调用模式：**

```python
def _start_stream(self, path, body, params=None):
    self._worker = StreamWorker(self._client, path, body, params, parent=self)
    self._worker.event.connect(self._on_sse_event)
    self._worker.finished_ok.connect(self._on_stream_done)
    self._worker.failed.connect(self._on_stream_failed)
    self._set_state("streaming")
    self._worker.start()

def _stop_stream(self):
    if self._worker and self._worker.isRunning():
        self._worker.stop()
        self._worker.wait(2000)
    self._set_state("idle")              # 中止 = 回 idle（不算 done，丢当前产物）
```

**`ScreenwriterClient.stream_post` 接受 params：**

```python
def stream_post(self, path: str, body: dict,
                params: dict | None = None) -> Iterator[dict]:
    with httpx.Client(timeout=None) as c:
        with c.stream("POST", f"{self.base_url}{path}",
                       json=body, params=params or {}) as resp:
            resp.raise_for_status()
            yield from parse_sse_lines(resp.iter_lines())
```

---

## 3. IdeatePage（创意子面板）

### 3.1 布局

```
IdeatePage（QSplitter Horizontal）
├── 左 _CandidatesPanel       约 38%
│   ├── QLabel "候选 (N)"
│   ├── QScrollArea {QVBoxLayout: [_CandidateCard × N]}
│   └── QPushButton "选定 c1 · 推进 →"      按钮文本依 _selected_id 变
└── 右 _ChatPanel              约 62%
    ├── 顶 [清空对话] 按钮（右上角）
    ├── 首次对话前显 _ContextForm（主旨/题材/时长/视觉风格/extra_constraints）
    ├── QLabel "聊天历史"
    ├── QScrollArea {QVBoxLayout: [_MessageBubble × N]}   自动滚到底
    └── QHBoxLayout
        ├── QPlainTextEdit (input, maxHeight=80)
        └── QPushButton "发送" / "▣ 中止"    按 _state 切
```

### 3.2 核心字段

```python
self._messages: list[dict]      # [{role, content}, ...] 持久化在 idea.json.messages
self._candidates: list[dict]    # [{id, title, angle, summary, highlights, ...}]
self._selected_id: str          # idea.json.selected_id
self._context: dict             # IdeateContext（主旨/题材/时长/...）
self._worker: StreamWorker | None
self._state: str                # "idle" | "streaming"
self._buf: str                  # 流式累积当前 assistant 消息
```

### 3.3 交互流程

**① `set_project(path)`：**
- `path=None` → 整页占位屏
- 有 path → 读 `idea.json`（若存在）→ 恢复 4 个字段 → 渲染左侧卡片 + 右侧气泡
- 未首次对话过 → 顶部显 _ContextForm；首次对话发完后 form 隐藏

**② 用户点[发送]：**
1. 当前 input 当 user message 追加到右侧气泡
2. body 含 project_dir + context + 完整 messages + auto_save_idea_json=True
3. 启动 StreamWorker(`/ideate/chat`)
4. 收 `event=delta` → `_buf += data["text"]`、最后一条 assistant 气泡追加（节流 50ms repaint）
5. 收 `event=done` → 重读 `idea.json`（Agent 已落盘并解析候选）→ 新 `_candidates` 重渲染左卡片

**③ 用户点候选卡片**：
- 本地标记 `_selected_id`（不立即调 select endpoint，避免误触）
- 按钮文本变 `"选定 c2 · 推进 →"`
- 用户点这个按钮：→ `client.ideate_select(project_dir, selected_id)`（同步 POST）→ emit `stageAdvanceRequested(1)` 给 ScreenwriterPanel

**④ 中止**：worker.stop() → 当前 assistant 气泡保留 + 加灰色 "(已中止)" 后缀；不写 idea.json（磁盘版保留上次成功版）

**⑤ 清空对话**：右上角 [清空对话] 按钮 → 弹确认 → 清 messages/candidates + 显回 ContextForm（不重置 context）

**⑥ 下游处理**：`/ideate/chat` 不支持 purge_downstream；剧本.md/分镜.json/prompts/ 不动；推进到剧本阶段时由 ScriptPage 自检"上游 idea 比下游剧本新 → 提示是否重生"

---

## 4. ScriptPage（剧本子面板）

### 4.1 布局

```
ScriptPage（QVBoxLayout）
├── 顶 _ParamBar
│   ├── 时长 QSpinBox  fps QSpinBox  语言风格 QComboBox
│   ├── ── 弹性间隔 ──
│   ├── QLabel "● 流式 · 已 N 字"             _state=streaming 时显
│   ├── QPushButton "生成剧本" / "▣ 中止"
│   └── QPushButton "▣ 中止"                   streaming 时显在 [生成] 旁
├── 中 QPlainTextEdit（_editor，可编辑）          1 stretch
└── 底 _ActionBar
    ├── QPushButton "💾 保存修改"               editor.modified 时高亮
    ├── QPushButton "📂 打开文件"                QDesktopServices.openUrl
    ├── ── 弹性间隔 ──
    └── QPushButton "推进到分镜 →"               _state=done + 无 dirty 时启用
```

### 4.2 核心字段

```python
self._editor: QPlainTextEdit
self._project_dir: Path | None
self._script_path: Path | None      # project_dir / "剧本.md"
self._worker: StreamWorker | None
self._state: str                    # "idle" | "streaming" | "done"
self._original_text: str            # 最近"已保存/已落盘"的文本，判 dirty
self._last_load_mtime: float        # 外部修改检测
```

### 4.3 交互流程

**① `set_project(path)`：**
- `None` → 占位屏
- 有 path → `_script_path = path / "剧本.md"`。若存在 → 读到 `_editor`、`_original_text = editor.toPlainText()`、`_state = "done"`；不存在 → editor 空、`_state = "idle"`
- 参数行从 cfg 读默认（duration_sec/fps/language_style）

**② 点 [生成剧本]：**
- 上游检查：缺 `idea.json` 或 `selected_id` 空 → 弹 warning "请先在「创意」阶段选定一个候选"
- `_state == "done"` 已存剧本 → 弹覆盖确认 "重新生成会覆盖剧本.md，并删除下游 分镜.json + prompts/。继续？" → 同意才往下 + `params={"purge_downstream":"true"}`
- editor.clear()，`_buf=""`，`_state="streaming"`
- StreamWorker(`/script`)
- 收 `delta` → `_editor.insertPlainText(data["text"])`（追加在末尾、节流 50ms）；字数 label 更新
- 收 `done` → 重读磁盘 `剧本.md` → `_editor.setPlainText(disk); _original_text=disk; _state="done"`

**③ 编辑/保存：**
- editor `textChanged` → `_save_btn.setEnabled(editor.toPlainText() != _original_text)`
- 点 [保存] → `atomic_write_text(_script_path, editor.toPlainText())`；更新 `_original_text` + `_last_load_mtime`
- 切阶段/切项目/关窗时调 `try_release()`：dirty 则弹 [保存/丢弃/取消]——取消则阻断切换

**④ 中止**：worker.stop() → editor 保留累积文本但不写盘；`_state` 回 `"idle"`

**⑤ 推进到分镜**：`_state=="done"` 且无 dirty 时 enabled → emit `stageAdvanceRequested(2)`

**⑥ 外部修改兼容**：ScreenwriterPanel 在 `_switch_stage` 时检测 `_script_path.stat().st_mtime > self._last_load_mtime` → 弹 "剧本.md 已被外部修改，重载？[是][否]"

---

## 5. StoryboardPage（分镜子面板）

### 5.1 布局

```
StoryboardPage（QVBoxLayout）
├── 顶 _ParamBar
│   ├── 比例 QComboBox(9:16/16:9/1:1)  fps QSpinBox  默认时长 QDoubleSpinBox  密度 QComboBox
│   ├── ── 弹性间隔 ──
│   ├── QLabel "● 流式 · 已 N 字 · 修复中…"
│   └── QPushButton "生成分镜" / "▣ 中止"
├── 全局头 _GlobalHeader（QWidget）              显当前 分镜.json 顶层字段；可改
│   ├── 标题 QLineEdit  比例 QLineEdit  时长 QSpinBox（只读，按 shots 自动算）
│   ├── globalStyle QPlainTextEdit（高度 50）
│   └── characters：每行 _CharacterRow + [+ 加角色]
├── 中 _ShotsTableView（QTableView）             双击单元格内联编辑；右键菜单
│   列：ID | 时长(s) | 构图 | 描述 | stylePrompt
└── 底 _ActionBar
    ├── _WarningsBanner                          点行号跳表格对应行
    ├── ── 弹性间隔 ──
    ├── QPushButton "💾 保存修改"
    ├── QPushButton "{ } 看原始 JSON"             弹只读 QDialog 显 formatted JSON
    └── QPushButton "推进到提示词 →"
```

### 5.2 核心字段

```python
self._project_dir: Path | None
self._sb_path: Path | None              # project_dir / "分镜.json"
self._sb: dict | None                   # 当前内存版
self._original_sb_json: str             # 最近落盘版的 json string，判 dirty
self._shots_model: _ShotsTableModel     # QAbstractTableModel 包装 _sb["shots"]
self._warnings: list[dict]              # Agent done 时传回
self._worker, self._state, self._buf, self._last_load_mtime
```

### 5.3 流式接收设计（关键，跟剧本/提示词不同）

分镜的 LLM 输出是**一整段 JSON**，全文 stream 完才能完整 parse。UX 上：
- 收 `delta` → 追加到内部 `_buf`，**不立即 parse**；顶部字数 label 更新
- 收 `status="validating"` → label 变 "修复中…"
- 收 `done` → `_sb = data["result"]; _warnings = data["warnings"]; _original_sb_json = json.dumps(_sb)` → 重渲染全局头/角色/表格 + warnings 红条；`_state="done"`
- 收 `error` → 专属对话框：
  - `JSON_REPAIR_FAILED` → 按钮 [打开 raw 文件] + [关闭]
  - `SCHEMA_VALIDATION_FAILED` → message + hint + [关闭]

### 5.4 Warnings 红条

```
⚠ 2 warnings · ▸ shots[1].stylePrompt 过短  ▸ characters[0].appearance 过短
```
- info=灰、warning=黄、error=红、critical=红底
- 红条高度按行数自适应（最多 5 行 + 滚动）
- 点 warning → 解析 `path` 字段（如 `shots[1].stylePrompt`） → 跳表格高亮对应**行**（cell 高亮延后 P2）

### 5.5 内联编辑 + dirty

- `_ShotsTableModel.setData` 每次单元格改完 emit `dataChanged` → page 监听 → `_dirty=True` → [保存] enabled
- 全局头/角色区每个 QLineEdit `textChanged` 同样触发 dirty
- [保存] → 用 `Storyboard` pydantic 模型 `model_validate` 一次（防用户改坏 schema）→ `atomic_write_text(json)` → `_original_sb_json` 更新 → dirty 归零

### 5.6 看原始 JSON 弹窗

只读 QDialog，按钮 [复制到剪贴板] + [打开文件] + [关闭]。

### 5.7 重生 / 推进 / 外部编辑

同 ScriptPage 模式：弹覆盖确认 + `purge_downstream=true`；外部 mtime 检测+提示重载；`_state=="done"` 且无 dirty 时推进 enabled。

---

## 6. PromptsPage（提示词子面板）

### 6.1 布局

```
PromptsPage（QVBoxLayout）
├── 顶 _ParamBar
│   ├── grid QComboBox(single/4/9)  角色参考 QCheckBox  画质增强 QCheckBox
│   ├── ── 弹性间隔 ──
│   ├── QLabel "● 角色 1/1 · 网格 2/3"   流式时显
│   └── QPushButton "生成提示词" / "▣ 中止"
└── 主区 QSplitter Horizontal
    ├── 左 _ProductTree                            约 35%
    │   ├── 📁 角色参考图 (N)
    │   │   ├── ●/✓/○ 狐妖_ref.md
    │   │   └── ○     书生_ref.md
    │   ├── 📁 N 宫格 (M)
    │   │   ├── ✓ S1.md
    │   │   ├── ● S2.md  (流式中)
    │   │   └── ○ S3.md
    │   └── ── 底部 [📂 打开 prompts/]
    └── 右 _Preview                                  约 65%
        ├── QLabel "预览: 狐妖_ref.md"
        ├── QPlainTextEdit  当前文件内容；可编辑
        └── QHBoxLayout [💾 保存] [完成 ✓]
```

### 6.2 核心字段

```python
self._project_dir: Path | None
self._prompts_dir: Path | None              # project_dir / "prompts"
self._sb: dict | None                       # 分镜.json 缓存，知道有哪些 character/shot
self._tree_items: dict[Path, QTreeWidgetItem]   # 文件路径 → tree item，partial 事件按路径定位
self._current_file: Path | None
self._original_text: str                    # 当前选中文件最近落盘版
self._worker, self._state, self._buf, self._last_load_mtime
```

### 6.3 占位项 + 状态点

- ○ 灰：未生成（按 `_sb` 推算预期文件）
- ● 蓝：流式中
- ✓ 绿：已落盘存在

预期文件按 `_sb["characters"]` 推 `<name>_ref.md`；按 `grid_mode` 推 `S1.md, S2.md, ...`。分镜.json 缺角色 → 树里就没有"角色参考图"占位分组。

### 6.4 流式生成

- 点 [生成提示词] → 上游检查（`分镜.json` 不存在 → 弹警告）→ 重生确认（`prompts/` 非空时弹"会清空 prompts/，继续？"，带 `purge_downstream=true`）
- StreamWorker(`/prompts`)
- 收 `partial` → `data={"saved":"...","kind":"character_ref"|"grid_prompt"}` → 找树 item（按 path）→ 状态点变 ✓ + 读文件 → 当前预览就是它则刷右侧 preview
- 收 `done` → 整树最终 ✓，`_state="done"`

> partial 比 delta 简单：Agent 一个文件完整生成完才发 partial（已落盘）；UI 不管"流式累积到哪个文件"——直接看磁盘

### 6.5 右侧预览编辑

- 选树文件 → editor 显内容、记 `_original_text`、`_last_load_mtime`
- editor `textChanged` → [保存] enabled
- 切文件/切阶段/切项目时调 `try_release()`：dirty 则弹 [保存/丢弃/取消]
- [保存] → `atomic_write_text(_current_file, editor.text())`

### 6.6 完成 ✓

- 本期最末阶段，按钮 `"完成 ✓"`
- 点击 → emit `projectCompleted` 给 ScreenwriterPanel
- panel 弹 `statusMessage.emit("项目「XXX」已完成 ✓")` + `refresh()`（更新 master 状态）
- **不切阶段**，保持在 prompts 页

### 6.7 部分重生延后 P2

本期 MVP 只支持全量重生。"只重新生成 S2.md" 留作未来增强；spec § 8 已记录。

---

## 7. ScreenwriterPanel 改造 + 集成

### 7.1 既有部分（不动）

- master：项目列表 + 按钮（新建/打开/删除）+ viewport eventFilter + status_color
- detail 顶部：项目名 QLabel + 4 阶段标签 QButtonGroup
- `_switch_stage(idx)` 方法

### 7.2 改造点

1. **删 wizard 占位子面板**：当前 `_build_detail` 里 `for stage_idx in _STAGE_NAMES:` 那段占位（QLabel+QPlainTextEdit+两按钮）全删
2. **装配 4 个真实子面板**：

```python
from .screenwriter.ideate_page import IdeatePage
from .screenwriter.script_page import ScriptPage
from .screenwriter.storyboard_page import StoryboardPage
from .screenwriter.prompts_page import PromptsPage

self.wizard = QStackedWidget()
self._stage_pages = [
    IdeatePage(self._client, self),
    ScriptPage(self._client, self),
    StoryboardPage(self._client, self),
    PromptsPage(self._client, self),
]
for p in self._stage_pages:
    self.wizard.addWidget(p)
    p.stageAdvanceRequested.connect(self._switch_stage)
    p.projectStateChanged.connect(self.refresh)
    p.statusMessage.connect(self.statusMessage)
```

3. **3 个跨阶段公共信号**（每个子面板都 emit）：

```python
class _BaseStagePage(QWidget):
    stageAdvanceRequested = Signal(int)     # 推进到第几个阶段（0..3）
    projectStateChanged = Signal()          # 产物变化 → master 列表状态点要刷
    statusMessage = Signal(str)             # toast 到主窗状态栏
```

4. **`set_project(path)` 级联**：`_on_row_selected` 时给所有 4 个子面板调 `set_project(path)`；推进时不再调（子面板已 hold path）

5. **dirty 切换护栏**：用户切阶段 / 切项目时，调当前可见 page 的 `try_release() -> bool`：False 阻断切换

6. **删 `_on_generate_stage` 和 `_on_open_output`**——所有生成/打开/保存逻辑搬进子面板

7. **`refresh()` 加 stale 检测**：扫项目时检测 `_pre stage_mtime > _next stage_mtime`，状态色用 status_color；本期不强阻断，只在 master 显文字

8. **`projectCompleted` 接收**：PromptsPage 完成 ✓ → ScreenwriterPanel `statusMessage` toast + `refresh()`

---

## 8. 错误处理 / 测试 / 风险

### 8.1 错误处理

| 场景 | 处理 |
|---|---|
| **SSE 网络错误**（worker.failed） | 子面板状态回 idle + `QMessageBox.warning("生成失败：{原因}\n请检查网络或 LLM 配置")` |
| **Agent 子进程未启动** | master 列表静默渲染，状态"Agent 未就绪"；子面板 [生成] 按钮禁用 + tooltip "等待 Agent 启动" |
| **上游产物缺失** | 子面板内点 [生成] 时主动检测（不依赖 Agent 返回 UPSTREAM_PRODUCT_MISSING）；缺 → 弹 warning "请先完成「{上游阶段}」" |
| **SSE done 时 Agent 返回 error 事件** | JSON_REPAIR_FAILED → [打开 raw 文件] + [关闭]；其它 → message + hint + [关闭] |
| **磁盘 IO 失败** | 弹 warning "保存失败：{原因}"；editor 保持 dirty |
| **外部修改未保存冲突** | _save() 前对比磁盘 mtime > 上次 load 的 mtime → 弹 "{文件}已被外部修改，覆盖还是丢弃本地改动？[覆盖] [重新加载] [取消]" |

### 8.2 测试策略

每个子面板各 1 个 smoke 测试文件，offscreen QApplication：

| 文件 | 覆盖点 |
|---|---|
| `test_stream_worker.py` | 注入 stub client，验证 event/finished_ok/failed 信号正确发出；stop() 触发后 worker 退出 |
| `test_ideate_page.py` | 空项目 → set_project → ContextForm 可见；fixture 含 idea.json → 候选卡片渲染数量正确；本地选中改 _selected_id，不立即触发 ideate_select |
| `test_script_page.py` | set_project 空 → 占位；fixture 含剧本.md → editor 加载；状态机迁移 idle/streaming/done；editor 改动 → 保存按钮启用 |
| `test_storyboard_page.py` | fixture 含分镜.json + warnings → 全局头/表格/warnings 渲染；点 warning 跳对应行；表格内联编辑 → dirty |
| `test_prompts_page.py` | fixture 含 prompts/* + 分镜.json → 树状态点正确（✓/○）；切文件时未保存触发对话框 |
| `test_screenwriter_panel_integration.py` | 4 子面板装配 OK；_switch_stage 切换 + dirty 阻止；projectCompleted 信号路径 |

**所有 SSE 流的端到端测试**：mock `client.stream_post` 返回 fixture event 列表，**不起真 Agent 子进程**。Agent 后端的 `test_e2e_smoke.py` 仍跑真 fastapi TestClient 兜底。

**计划任务量**：4 个子面板 + StreamWorker + ScreenwriterPanel 改造 + 6 个测试文件 ≈ **15–18 个 task**，1 个 phase。

### 8.3 风险与缓解

| 风险 | 缓解 |
|---|---|
| 流式期间 QPlainTextEdit 频繁 insertPlainText 卡 UI | `delta` 事件 50ms 节流（QTimer.singleShot 攒一批后 flush） |
| Storyboard 流式期间无法实时解析 N 镜头 | 流式期间不解析、只显字数；done 时一次性解析 + 渲染表格（用户已接受） |
| StreamWorker 没清理就被父 widget 销毁 | 子面板 closeEvent 调 `_stop_stream()` + wait(2000) 后再 deleteLater；ScreenwriterPanel `set_project(None)` 时也调一遍 |
| Agent 死活不返回 done（卡住） | StreamWorker 不设强超时（LLM 可能合法地跑 5 分钟）；交给用户手动 [▣ 中止] |
| idea.json 候选解析靠启发式（spec Task 12 已知简陋） | 候选卡片渲染兜底：candidates 空但有 raw_text → 渲染 1 张 _RawTextCard 显原文 |

### 8.4 显式延后到 P2（不在本期）

- 创意阶段聊天面板美化（时间戳、markdown 渲染、用户头像）
- 分镜阶段镜头拖拽排序、批量编辑
- 提示词阶段单文件部分重生（"只重做 S2.md"）
- 流式取消的细化（spec §3.9 客户端断连即取消，已是这个模式但没做单元测试）
- warnings 行号到表格 cell 的精准高亮（本期是跳行，cell 高亮 P2）

---

## 9. 参考资料

- 上游 spec：`docs/superpowers/specs/2026-05-28-screenwriter-agent-design.md`
- 上游 plan：`docs/superpowers/plans/2026-05-28-screenwriter-agent-mvp.md`（已实施）
- 既有控件 `ScreenwriterPanel`：`drama_shot_master/ui/panels/screenwriter_panel.py`
- 既有 client：`drama_shot_master/agents/screenwriter_client.py`
- Agent SSE event 协议：spec §3.0
- 重做下游清理：spec §3.10

---

**完。**
