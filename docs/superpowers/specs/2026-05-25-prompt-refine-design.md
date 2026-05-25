# 一键提示词反推优化（Prompt Refine）设计

**项目**：drama-shot-master
**版本**：v0.7.x 增量（设计阶段）
**日期**：2026-05-25
**状态**：设计评审通过，待写实现 plan
**关联**：视频面板 `video_panel.py` + `TimelineModel` + vision provider 体系。
**参考**：`E:\Rui\笔记\AIEngineer\AIEngineer\漫剧\01-Workflow配置\04-分镜生成\LTX2.3：meta-prompts.md`（LTX 2.3 提示词知识来源）。

---

## 1. 背景与目标

### 1.1 问题

视频面板里 prompt 窗常是粗糙英文。用户想一键把 **全局 prompt + 所有分镜图 + 各段局部 prompt** 交给图片理解模型，结合 LTX 2.3 提示词工程知识，获得更精确的提示词，并自主决定是否替换。

### 1.2 目标

视频面板加一个「✨ 优化提示词」按钮：收集 global + 所有段（image 段附图、text 段仅文本）→ 调当前 vision provider（注入 LTX 2.3 meta-prompt 系统提示词，要求 JSON 输出）→ 弹窗逐行展示 before/after，用户逐行勾选是否替换。

### 1.3 非目标

- 不替换现有 `InferencePanel`（那是模板驱动的从零反推；本功能是已有 prompt 的精炼）
- 不让模型改时长 / guide_strength（仅 prompt 文本）
- 不做弹窗内手动编辑精炼文本
- 不做精炼历史 / 撤销
- 不做流式进度

---

## 2. 关键决策（评审 Q&A）

| 决策点 | 选择 | 理由 |
|---|---|---|
| 精炼范围 | global + 所有段 local | 用户原话"获得更精确的提示词" |
| 应用粒度 | 逐行勾选 + 全部应用/全部取消便捷键 | 用户要求最灵活 |
| 段范围 | image 段 + text 段都参与 | text 段也有 local_prompt |
| meta-prompt 存储 | 可编辑 bundled 文件 `templates/ltx_refine_meta_prompt.md` | 调提示词无需改代码 |
| 按钮位置 | 图片池 toolbar 右侧，与 Add Text/Audio 并列 | 全局动作 |
| 弹窗精炼文本 | 只读（应用后去原框改） | YAGNI |
| provider | 复用 `cfg.current_provider` / `current_model` | 与 InferencePanel 一致 |

---

## 3. 架构

| 单元 | 文件 | 职责 | 依赖 |
|---|---|---|---|
| Meta-prompt 资源 | `templates/ltx_refine_meta_prompt.md`（新增） | LTX 2.3 知识 + 强制 JSON 输出契约 | 无 |
| 精炼逻辑 | `drama_shot_master/core/prompt_refiner.py`（新增） | 构造请求 + 解析响应（纯函数，Qt-free） | 无 Qt |
| Review 弹窗 | `drama_shot_master/ui/widgets/refine_review_dialog.py`（新增） | 逐行 before/after + 勾选 + 全选/全不选 | PySide6 |
| 面板集成 | `drama_shot_master/ui/panels/video_panel.py`（改） | 按钮 + worker + 弹窗 + 回写 model | factory / FunctionWorker |

边界：`prompt_refiner.py` 无 Qt 依赖、可单测；`refine_review_dialog.py` 是纯 UI；`video_panel.py` 只做编排（收集→调用→应用）。

---

## 4. 详细设计

### 4.1 meta-prompt 资源 `templates/ltx_refine_meta_prompt.md`

改写自参考文件，保留核心知识，**改输出格式为 JSON**。要点：
- 角色：LTX 2.3 提示词工程师，对已有 prompt + 参考图做精炼
- 注入：六元素框架、九法则（含反 PPT 三件套）、七禁忌、长度准则、I2V/T2V 模式区分
- 输入说明：用户消息会给 global_prompt + 每段 `index / 有无图 / 时长秒 / 当前 local_prompt`；image 段对应的图按 index 顺序随附
- **输出契约（硬性）**：只输出一个 JSON 对象，不要 markdown 围栏、不要解释：
  ```json
  {
    "global_prompt": "refined ...",
    "segments": [{"index": 0, "local_prompt": "refined ..."}]
  }
  ```
- image 段按 I2V 规则（不重述静态、mouth moves naturally）；text 段按 T2V 规则（六元素全配）

### 4.2 `prompt_refiner.py`

```python
@dataclass
class RefineRequest:
    images: list[Path]          # image 段的图，按段序
    user_message: str           # 描述 global + 每段
    seg_ids: list[str]          # 按段序的 seg_id，用于把 index 映射回段

@dataclass
class RefineResult:
    global_prompt: Optional[str]            # None = 模型没给
    segment_locals: list[tuple[str, str]]   # [(seg_id, refined_local)]
    warnings: list[str]                     # 段数不匹配等


def build_refine_request(model: TimelineModel) -> RefineRequest:
    """收集 global + 所有段 → 模型输入。

    images 仅含 image 段的 image_path（按 model.segments 顺序）。
    user_message 用文本列出 global_prompt + 每段：
      [seg 0] type=image, 时长=1.50s, 当前: "<local>"
      [seg 1] type=text,  时长=0.50s, 当前: "<local>"
    seg_ids 为全部段（image+text）的有序 seg_id。
    """

def parse_refine_response(raw: str, seg_ids: list[str]) -> RefineResult:
    """解析模型 JSON 输出。

    容错：
    - 剥离 ```json / ``` 围栏与首尾空白
    - json.loads 失败 → raise RefineParseError(原始片段)
    - global_prompt 缺失 → RefineResult.global_prompt = None
    - segments 里 index 越界 / 缺失 → 跳过该项并记 warnings
    - 只映射 index 在 [0, len(seg_ids)) 的项
    """

REFINE_META_PROMPT_PATH = Path("templates/ltx_refine_meta_prompt.md")

def load_refine_meta_prompt() -> str:
    """读 meta-prompt 文件全文。缺失 → raise FileNotFoundError。"""
    return REFINE_META_PROMPT_PATH.read_text(encoding="utf-8")
```

`RefineParseError(Exception)` 也定义在本模块。`load_refine_meta_prompt()` 放此模块（Qt-free、可单测路径），面板 import 调用。

### 4.3 `refine_review_dialog.py`

```python
class RefineReviewDialog(QDialog):
    """逐行 before/after + 勾选。

    构造入参：
      rows: list[RefineRow]   # RefineRow(key, label, original, refined)
        key="global" 或 seg_id
    accepted_keys() -> set[str]   # 用户勾中的 key（exec 返回 Accepted 后读）
    """
```
- 顶部说明 + 「全部应用」「全部取消」两个按钮（切换所有勾选框）
- 中部 QScrollArea：每行 = 勾选框 + 标签（"全局" / "段 N（image/text）"）+ 左只读原文 + 右只读精炼
  - 精炼为空或与原文相同的行：默认不勾、标灰
- 底部「应用勾选」(Accepted) / 「取消」(Rejected)
- 模态 exec()

### 4.4 `video_panel.py` 集成

- toolbar 增 `self.btn_refine = QPushButton("✨ 优化提示词")`，加到 `pool_toolbar`（与 Add Text/Audio 并列）
- `_wire()` 接 `self.btn_refine.clicked.connect(self._on_refine)`
- 新增方法：

```python
def _on_refine(self):
    if not self.model.segments:
        QMessageBox.information(self, "无内容", "时间轴为空，先添加分镜段"); return
    try:
        provider = factory.build_provider(
            self.cfg, self.cfg.current_provider, self.cfg.current_model)
    except Exception as e:
        QMessageBox.critical(self, "Provider 错误", str(e)); return
    try:
        system_prompt = load_refine_meta_prompt()   # 读 templates 文件
    except FileNotFoundError:
        QMessageBox.critical(self, "缺少 meta-prompt",
                             "templates/ltx_refine_meta_prompt.md 不存在"); return
    req = build_refine_request(self.model)
    def task():
        raw = provider.generate(req.images, system_prompt, req.user_message)
        return parse_refine_response(raw, req.seg_ids)
    self.video_status_bar.set_status("优化中…")
    self._refine_worker = FunctionWorker(task)
    self._refine_worker.finished_with_result.connect(self._on_refine_done)
    self._refine_worker.failed.connect(
        lambda e: QMessageBox.critical(self, "优化失败", e))
    self._refine_worker.start()

def _on_refine_done(self, result: RefineResult):
    rows = []
    if result.global_prompt is not None:
        rows.append(RefineRow("global", "全局",
                              self.model.global_prompt, result.global_prompt))
    for seg_id, refined in result.segment_locals:
        seg = next((s for s in self.model.segments if s.seg_id == seg_id), None)
        if seg is None:
            continue
        label = f"段 {self.model.segments.index(seg)}（{seg.segment_type}）"
        rows.append(RefineRow(seg_id, label, seg.local_prompt, refined))
    if result.warnings:
        self.statusMessage.emit("；".join(result.warnings))
    dlg = RefineReviewDialog(rows, self)
    if dlg.exec() != QDialog.Accepted:
        self.video_status_bar.set_idle(); return
    accepted = dlg.accepted_keys()
    if "global" in accepted and result.global_prompt is not None:
        self.model.global_prompt = result.global_prompt
    for seg_id, refined in result.segment_locals:
        if seg_id in accepted:
            self.model.update_segment(seg_id, local_prompt=refined)
    self.global_form.set_state(self.model)
    self.timeline.rebuild()
    self.video_status_bar.set_idle()
```

`load_refine_meta_prompt()`（在 `prompt_refiner.py`）读 `templates/ltx_refine_meta_prompt.md` 全文；文件缺失 → `_on_refine` 里 try/except 提示后 return。

---

## 5. 数据流

```
[点 ✨ 优化提示词]
  → 校验非空 + build_provider
  → build_refine_request(model) → (images, user_message, seg_ids)
  → [worker] provider.generate(images, meta_prompt, user_message)
  → parse_refine_response(raw, seg_ids) → RefineResult
  → RefineReviewDialog(rows) 逐行勾选
  → 应用勾选：global → model.global_prompt；local → model.update_segment
  → global_form.set_state + timeline.rebuild
```

---

## 6. 错误处理

| 场景 | 行为 |
|---|---|
| 时间轴为空 | 提示后 return |
| provider 构建失败 | QMessageBox.critical |
| generate 抛错 | worker.failed → QMessageBox.critical |
| JSON 解析失败 | RefineParseError → 弹窗显示原始返回片段 |
| 段数不匹配 / index 越界 | 能映射的映射，缺的跳过 + statusMessage 提示 warnings |
| 模型没返回 global | 弹窗里不出现 global 行 |
| 用户取消弹窗 | 不改任何 model，status 复位 |

---

## 7. 测试

### 7.1 单元测试 `tests/test_core/test_prompt_refiner.py`

针对 Qt-free 的 `prompt_refiner`：

| 用例 | 验证 |
|---|---|
| build_request_collects_images | 2 image + 1 text 段 → `images` 含 2 路径（仅 image 段，按序） |
| build_request_seg_ids_ordered | `seg_ids` 含全部 3 段、顺序与 model.segments 一致 |
| build_request_message_has_all | `user_message` 含 global_prompt 文本 + 3 个段条目（index 0/1/2） |
| parse_valid_json | 合法 JSON → global + 2 段 locals 正确映射到 seg_ids |
| parse_strips_code_fence | 带 ` ```json … ``` ` 围栏 → 正常解析 |
| parse_missing_global | JSON 无 global_prompt → `result.global_prompt is None` |
| parse_index_out_of_range | segments 含 index=99 → 跳过 + warnings 非空 |
| parse_bad_json | 非 JSON 文本 → raise RefineParseError |

### 7.2 手测清单

1. 视频面板放 2-3 张图成段 + 1 text 段，各填粗糙 local，global 填一句。
2. 点「✨ 优化提示词」→ 状态栏"优化中…" → 弹窗出现，global + 每段一行 before/after。
3. 勾部分行 → 「应用勾选」→ 只有勾中的被替换（global_form / SegmentEditor 里核对）。
4. 「全部应用」「全部取消」按钮正确切换所有勾选框。
5. 取消弹窗 → model 不变。
6. 断网或填错 API → 弹"优化失败"，不崩。
7. 改 `templates/ltx_refine_meta_prompt.md` 后重跑 → 行为随之变化（验证文件可编辑生效）。

---

## 8. 依赖与影响面

- 零新增 pip 依赖（复用 provider/factory/FunctionWorker）
- 新增 2 个 py 文件 + 1 个 md 资源；改 `video_panel.py`
- 向后兼容：纯新增功能，不动现有信号 / 提交链路 / InferencePanel

---

## 9. 不做的事（YAGNI 清单）

- ❌ 替换 / 改动现有 InferencePanel
- ❌ 弹窗内编辑精炼文本
- ❌ 精炼历史 / 撤销
- ❌ 模型改时长 / guide_strength
- ❌ 流式进度细分
- ❌ 多 provider 并行对比
- ❌ meta-prompt 的可视化编辑器（直接改 md 文件）
