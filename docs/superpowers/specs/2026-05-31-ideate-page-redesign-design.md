# 立意页（剧本创作入口）重设计 — 题材/风格结构化 + 画幅

> 日期：2026-05-31　分支：main
> ② 核心的前端落点：把 `ideate_page` 的自由文本题材/视觉风格 → 结构化选择器（兼容保留自由文本），并加画幅选择。设计已可视化确认 `docs/explorer/screenwriter-ideate-redesign-confirm.html`。
> **实现时机：等 `ideate_page.py` 那边（会话前 M 文件，他人在改）稳定后再做**——用户会提醒。可独立先建的新 widget（AspectRatioSelector）不受此限。

## 已锁定决策

- **题材/风格 = 结构化为主 + 自由文本折叠高级（兼容方案）**：题材接 `GenrePickerDialog`（已建，result {genre,sub}），风格接 `StyleBibleDialog`（已建，result {ref,category}）；显示 chip + 选模板按钮；自由文本（原 `_ctx_genre`/`_ctx_visual`）折叠进「高级」面板（默认收起）。
- **画幅**：4 预设 `9:16(竖) / 16:9(横) / 1:1(方) / 4:5(竖)` + **自定义**（W:H 输入）。**默认 16:9**（短剧不限竖屏），**记住上次**（读/写 cfg.last_aspect_ratio）。可视化比例形状 + 用途副标。
- **布局**：沿用现有 ideate 的 QSplitter——左配置表单 + 右立意候选区（右侧不动）。
- **画幅存** `project.json.params.aspect_ratio`（项目级，驱动出图/视频）。题材存 `params.genre`(+sub)，风格存 `style_bible.ref`，集数/时长存 `params.episode_count`/`duration_per_unit_sec`。
- **注入预览**：左表单底部显示"本次生成将注入"——用 `gen_context.build_genre_context`/`build_style_context` 摘要 + 规格（画幅/集数/时长）。把 ② 核心可视化。
- 蓝紫主题、表单分组、渐进披露（高级折叠）、tabular 数字。

## 组件

### 1. AspectRatioSelector（新 widget，可独立先建，不碰 ideate_page）

`drama_shot_master/ui/widgets/aspect_ratio_selector.py`：
```python
class AspectRatioSelector(QWidget):
    changed = Signal(str)   # 如 "16:9" / "9:16" / 自定义 "21:9"
    _PRESETS = [("9:16","竖屏·抖音"),("16:9","横屏·影视"),("1:1","方·社媒"),("4:5","竖·小红书")]
    def value(self) -> str: ...          # 当前比例字符串
    def set_value(self, ratio: str): ... # 设当前（含自定义解析）
    # 分段按钮(可视形状) + 自定义 W:H 输入；选中 emit changed。
```
- 纯 widget，smoke 可测；记住上次由调用方（ideate）从 cfg 读 set_value、changed 时写 cfg。

### 2. IdeatePage 改造（等 ideate_page.py 稳定）

`drama_shot_master/ui/widgets/screenwriter/ideate_page.py`（M 文件，待协调）：
- 左表单重排为分组：创意(主旨) / 题材(picker+高级自由文本) / 风格圣经(picker+高级) / 画幅&规格(AspectRatioSelector + 集数/时长/候选数) / 注入预览 / 生成按钮。
- 题材 chip 显示当前 `params.genre`（display_name via load_genre）；点「选题材模板」→ GenrePickerDialog → 写 project.json.params.genre+sub + 刷新 chip。
- 风格 chip 显示当前 `style_bible.ref`；点「选风格圣经」→ StyleBibleDialog → 写 + 刷新。
- 画幅 AspectRatioSelector：初值 = project.json.params.aspect_ratio 或 cfg.last_aspect_ratio 或 "16:9"；changed → 写 params.aspect_ratio + cfg.last_aspect_ratio。
- 高级折叠：保留原 `_ctx_genre`/`_ctx_visual` QLineEdit，默认收起；其值仍进 request 的 genre_tags/visual_style（向后兼容叠加）。
- 注入预览：读 project.json genre/style → gen_context 摘要 + 规格，刷新显示。
- 生成请求：确保 request 带 project_dir（screenwriter_client 已据此自动注入 genre_context/style_context，波次2 已接）；自由文本仍填 genre_tags/visual_style。
- 右侧候选区不动。

## 数据契约

- `project.json.params`: `genre`(+`genre_sub`[])、`aspect_ratio`、`episode_count`、`duration_per_unit_sec`。`style_bible.ref`。
- `cfg.last_aspect_ratio`（settings.json，跨项目记忆默认）。

## 测试策略

- AspectRatioSelector smoke：4 预设 + 自定义；value/set_value round-trip；changed 发射；自定义 W:H 解析。
- IdeatePage（等实现）：题材/风格 chip 显示+点击弹 dialog 写 project.json（mock dialog）；画幅初值/changed 写 params+cfg；高级折叠默认收起、值进 request；注入预览随 project.json 刷新；生成 request 带 project_dir。

## 文件清单

```
新增(可独立先建)：
  drama_shot_master/ui/widgets/aspect_ratio_selector.py
  tests/test_ui/test_aspect_ratio_selector_smoke.py
改(等 ideate_page.py 稳定 + 协调)：
  drama_shot_master/ui/widgets/screenwriter/ideate_page.py
  tests/test_ui/screenwriter/test_ideate_page*.py（扩展）
```

## 范围/时机

- ✅ AspectRatioSelector 可独立先建（新文件，不碰 M 的 ideate_page）。
- ⏸ ideate_page 集成等用户提醒（ideate_page.py 是会话前 M 文件，他人在改，避冲突）。
- 兼容：自由文本保留；空 project.json genre/style → 行为同现状（降级）。
