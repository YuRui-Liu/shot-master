# 图像操作界面重构 · 设计规格

**项目代号**：shot-prompt-backwards v0.3
**日期**：2026-05-16
**状态**：设计评审中（待用户审阅 spec）
**前置版本**：v0.2（PySide6 桌面应用，6 个独立 Tab）

---

## 1. 背景与目标

### 1.1 问题

v0.2 把拆图/拼图/去白边/反推做成 6 个独立 Tab，用户反馈"太难用"，4 个具体痛点：

1. **路径要重填 3 次**：拆/拼/裁每个 Tab 独立填源路径+输出路径，同一目录的多步作业无法复用已加载缩略图
2. **拆图预览区太小**：没有"边框叠加预览"，只能看 100px 子图缩略图猜拆对没
3. **拼图点击顺序不直观**：没有蓝圈数字徽章，点错只能清空重选
4. **参数全靠手填**：没有"检测白边/推断网格"一键填参

### 1.2 目标

参照 `Projects/shot-master` 的三栏一体化交互模式，把 4 个功能（反推/拆图/拼图/去白边）重构为**共享一份目录状态的全局三栏布局**，并加目录记忆。

---

## 2. 范围

### 2.1 In Scope

- 全局三栏布局：左=目录/输出/状态，中=共享缩略图网格，右=功能切换器+参数+执行
- 4 个功能（反推/拆/拼/裁）共享同一份 `AppState`（目录、缩略图缓存、选择、输出目录）
- 缩略图徽章选择：multi 模式（高亮）/ order 模式（蓝圈①②③）
- 双击缩略图 → 大图预览对话框；拆图功能下叠加红线网格 overlay
- 拆图面板「检测白边」「推断网格」一键填参（复用 shot-master core 算法）
- 目录记忆：`settings.json` 记 `last_input_dir`/`last_output_dir`，启动自动加载
- 落地方式：**方案 B**（参照 shot-master 模式自主重写 UI，core 算法 import 不重写）

### 2.2 Out of Scope

- 不动 `core/`（template_engine/result_parser/output_writer/task_runner）
- 不动 `providers/`（4 个 vision 后端）
- 不动 `grid_ops.py`（shot-master 薄封装）
- 不重写 shot-master core 算法（detect_borders/infer_grid/split_image 等 import 复用）
- 不做 pytest-qt（dev 环境无 PySide6，沿用 v0.2 的 AST 检查 + 手动 smoke）

---

## 3. 整体布局

```
┌─────────────────────────────────────────────────────────────────────┐
│ 菜单: 文件(打开目录 Ctrl+O / 设置输出目录) · 帮助                       │
├──────────┬────────────────────────────────────┬─────────────────────┤
│ 左栏 220 │ 中栏（弹性，最大）                  │ 右栏 360            │
│ 当前目录 │  共享缩略图网格                     │ ┌反推│拆│拼│裁┐     │
│ [打开]   │  · IconMode 流式                   │ └─────────────┘     │
│ 输出目录 │  · multi=高亮 / order=蓝圈①②③      │ 参数表单(StackedW)  │
│ [设置]   │  · 双击→大图(可叠红线网格)         │ ───────────         │
│ N张 选M  │  · 底部:大小滑块 + 清空            │ [预览] [执行]       │
│ 状态信息 │                                    │                     │
└──────────┴────────────────────────────────────┴─────────────────────┘
 状态栏：当前后端·模型              进度条（执行时显示）
```

切功能只换右栏参数面板 + 中栏选择模式（multi↔order），**目录与缩略图缓存不动**。

---

## 4. 全局状态 AppState

`app/ui/state.py`：

```python
@dataclass
class AppState:
    current_dir: Optional[Path] = None
    images: list[ImageInfo] = field(default_factory=list)   # 缩略图缓存
    selected: list[int] = field(default_factory=list)        # 含点击顺序
    output_dir: Optional[Path] = None
    active_function: str = "inference"   # inference|split|combine|trim
```

`ImageInfo`：`{path: Path, pixmap_thumbnail: QPixmap | None}`（懒加载缩略图）。

### 4.1 目录记忆

`Config` dataclass 新增字段：`last_input_dir: Optional[str]`、`last_output_dir: Optional[str]`。

- `load_config()`：从 `.env` 读不到这俩（它们只存 settings.json），从 settings.json 读
- `update_settings()`：白名单加 `last_input_dir`/`last_output_dir`，落盘 settings.json
- 启动时 MainWindow 读 `cfg.last_input_dir`：路径存在 → 自动 `load_directory()` 铺缩略图；`last_output_dir` 回填左栏
- 用户每次成功「打开目录」「设置输出目录」→ 立即 `cfg.update_settings(last_input_dir=..., last_output_dir=...)`
- 路径失效（被删/移动）→ 静默回空状态，不弹错

---

## 5. 中栏组件

### 5.1 ThumbnailGrid（`app/ui/thumbnail_grid.py`，重写）

- `QListWidget` IconMode + 自定义 `ThumbnailDelegate`
- 选择模式由 `AppState.active_function` 决定：
  - `multi`（反推多图/拆图/去白边批量）：点击切换，蓝色描边
  - `order`（拼图）：点击累加，蓝圈①②③徽章；再点取消并重排后续序号
- 底部工具条：缩略图大小滑块（80–240px，存 settings.json `ui.thumb_size`）+「清空选择」
- 双击 → `previewRequested(int)` 信号

### 5.2 ThumbnailDelegate（`app/ui/thumbnail_delegate.py`，新）

`QStyledItemDelegate` 子类。`paint()` 读 item 的 `BADGE_ROLE` 数据，非 None 时用 `QPainter` 画 22px 蓝色实心圆 + 居中白色序号。multi 模式选中画蓝色描边。

### 5.3 PreviewDialog（`app/ui/preview_dialog.py`，新）

`QDialog`，可缩放图片视图：

- 普通预览：放大看原图
- 拆图 overlay 预览（active_function=='split' 时双击）：
  - 源网格 `src_rows × src_cols` 画红色实线（2px）
  - 子图分组 `sub_rows × sub_cols` 画红色虚线（1px）
  - margins/gap 按比例偏移
  - 坐标换算抽成纯函数 `compute_grid_lines(img_w, img_h, spec, display_w, display_h) -> list[Line]`（可单测，不依赖 Qt）
  - 顶部小字：`源 4×4 → 子 2×2 = 将切出 4 张`；参数不整除变红字报错、不画线、不崩
- 算法数学逻辑参照 shot-master `PreviewDialog` 的 overlay 实现（抄公式不抄代码）

---

## 6. 右栏：功能切换器 + 4 面板

右栏 = 顶部 4 按钮切换器 + `QStackedWidget`（4 面板）+ 底部统一 `[预览][执行]`。

### 6.1 BasePanel（`app/ui/panels/base_panel.py`）

抽象基类，定义接口：
- `validate() -> tuple[bool, str]`：参数是否合法 + 原因
- `execute()`：分派到具体操作（耗时走 QThread）
- `preview()`：拆/拼弹 PreviewDialog；反推无预览
- `select_mode() -> str`：返回 `"multi"` 或 `"order"` 给中栏

### 6.2 SplitPanel

- 网格：源 `src_rows×src_cols`、子 `sub_rows×sub_cols`（4 SpinBox）
- 白边：margins(上右下左)+gap；「检测白边」调 `shot_master.core.border_detector.detect_borders`，「推断网格」调 `infer_grid`（core 算法，import 复用）
- 输出格式 PNG/JPG
- 中栏 = multi（批量拆多张）
- execute：每张选中 → `grid_ops.split_to_files()` → 输出目录

### 6.3 CombinePanel

- 目标 `target_rows×target_cols`、gap、缩放 letterbox/crop/stretch、目标比例
- 中栏 = order
- 实时提示 `已选 N / 需 R×C=M`；不符则「执行」置灰
- 输出文件名（默认 `combined.png`）
- execute：`grid_ops.combine_to_file()` → 输出目录

### 6.4 TrimPanel

- 阈值、最大迭代、命名后缀（默认 `_trim`）、输出格式
- 中栏 = multi（选中几张裁几张；不选=裁整目录）
- execute：`grid_ops.trim_one()` 逐张 → 输出目录

### 6.5 InferencePanel

- 模式：单图 / 多图 / 宫格（"文件夹批量"退化——目录缩略图已在中栏，多选即批量）
- 模板下拉 + 自动推荐（按选中数）+ 模板变量动态表单（复用 v0.2 `widgets/template_form.py`）
- 宫格模式防灾门禁：选 1 张 → 设网格 → 双击看红线 overlay → 勾「我确认拆图正确」→ 才可执行
- execute：选中图（或宫格 tiles）→ provider.generate → 结果区可编辑保存
- 后台用 v0.2 `worker.py` 的 FunctionWorker/BatchWorker

### 6.6 文件结构

```
app/ui/
├── state.py                  # AppState + 目录记忆（新）
├── main_window.py            # 三栏 + 菜单 + 信号总线（重写）
├── thumbnail_grid.py         # 中栏缩略图（重写）
├── thumbnail_delegate.py     # 徽章 delegate（新）
├── preview_dialog.py         # 大图 + overlay 红线（新）
├── worker.py                 # FunctionWorker/BatchWorker（v0.2 保留）
├── widgets/
│   └── template_form.py      # v0.2 保留
└── panels/
    ├── base_panel.py         # 抽象基类（新）
    ├── split_panel.py        # 新
    ├── combine_panel.py      # 新
    ├── trim_panel.py         # 新
    └── inference_panel.py    # 新

删除：app/ui/tabs/（6 文件）、app/ui/widgets/thumbnail_list.py
保留不动：app/grid_ops.py、app/core/、app/providers/、app/main.py（入口不变）
修改：app/config.py（加 last_input_dir/last_output_dir 字段 + 持久化白名单）
```

---

## 7. 信号流

```
ThumbnailGrid.selectionChanged(list[int]) → AppState.selected → 右栏 validate() → [执行]可用性
ThumbnailGrid.previewRequested(int)       → MainWindow → active=='split' 则带 overlay 弹 PreviewDialog
功能切换器 clicked(str)                    → AppState.active_function → 切右栏面板 + 中栏选择模式
缩略图大小 slider                          → settings.json ui.thumb_size
打开目录/设置输出 成功                      → cfg.update_settings(last_input_dir/last_output_dir)
Worker.finished/failed                    → QMessageBox + 状态栏 + 右栏恢复
```

---

## 8. 错误处理

| 场景 | 行为 |
|---|---|
| 参数非法（拆不整除/拼数量不符/反推必填空） | 「执行」置灰 + 旁红字原因（不弹窗） |
| 目录记忆失效（last_input_dir 被删） | 静默回空状态，不弹错 |
| 执行期异常（API/算法/写盘） | QThread 捕获 → QMessageBox.critical → 状态栏「失败」→ 右栏恢复 |
| overlay 参数错（不整除） | 预览对话框顶部红字提示，不画线，不崩 |

---

## 9. 测试策略

- **纯逻辑单测**：
  - `tests/test_state.py`（新）— AppState 目录记忆读写、路径失效降级
  - `tests/test_config.py`（改）— 加 `last_input_dir`/`last_output_dir` 字段断言
  - `tests/test_overlay_lines.py`（新）— `compute_grid_lines()` 纯函数，给定尺寸+spec 断言线坐标
  - `grid_ops`/`core`/`providers` 现有 47 测试保持全绿（重构不动）
- **UI 层**：AST 语法检查 + 手动 smoke（启动后点 4 功能）

### 9.1 验收标准

- [ ] 启动即自动加载上次目录缩略图（若存在）
- [ ] 打开一次目录，4 功能共享，不再重填路径
- [ ] 拼图蓝圈①②③徽章，再点取消自动重排
- [ ] 双击缩略图弹大图；拆图下叠红线网格 + 顶部"将切出 N 张"
- [ ] 拆图有「检测白边」「推断网格」一键填参
- [ ] 输出目录设一次全局复用，记忆到下次启动
- [ ] `tests/` 现有 47 + 新增 state/config/overlay 测试全绿
- [ ] 启动后 4 功能手动 smoke 通过

---

## 10. 风险

| 风险 | 应对 |
|---|---|
| overlay 红线坐标换算（margins/gap 偏移）易错 | 抽纯函数 + 单测；数学公式参照 shot-master PreviewDialog |
| shot-master core API 变更 | detect_borders/infer_grid 是稳定 core 接口；已有 grid_ops 测试覆盖 |
| 重构破坏现有 47 测试 | core/providers/grid_ops 完全不动；只动 ui/ + config.py 加字段 |
| 目录记忆写 settings.json 与 provider 设置冲突 | update_settings 白名单显式列字段，互不覆盖 |

---

## 11. 下一步

1. 用户审阅本 spec
2. 通过后 → writing-plans skill 出实现计划
3. 按计划 subagent-driven 执行
