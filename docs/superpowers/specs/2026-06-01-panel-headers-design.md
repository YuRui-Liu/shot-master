# Panel Headers 编号/文案/样式统一

## 目标

将 ④⑤⑥⑦ 四个面板的顶部标题栏统一为分镜板 `.topbar h1` 的品牌渐变样式，同时重排编号、精简文案、规范化集数写法。

## 范围

仅动 HTML/CSS 的标题栏文案、编号、渐变样式；不动 JS 逻辑、后端 API、文件命名。

---

## 改动清单

### 1. `web/video-mode2.html` — ④ 视频生成 · CLIPS

**标题渐变：** `.work-head h1` 加 `linear-gradient(135deg, var(--blue), var(--mauve))` + `background-clip: text` + `color: transparent`

**工作模式上移：** 从独立 `.modebar` 行移到 `.work-head` 内部，位置在 `h1` 右侧、「剧集下拉框」左侧。

**元素顺序（从左到右）：**
1. `<h1>` — 渐变标题（含 `· 任务N` 后缀）
2. `<div class="seg">` — 工作模式切换按钮组
3. `<select class="shot-select">` — 剧集选择下拉
4. `<div class="task-switch">` — 并行任务（`margin-left: auto` 右对齐）

**modebar 行删除。** `.modebar` CSS 块可保留（无副作用），其 HTML 元素删除。

**工作模式按钮文案（保持原样）：**
- 模式1 · 高自由度·导演台
- 模式2 · 剧集分镜对齐

### 2. `web/compose.html` — ⑤ 智能转场 · Transition

| 位置 | 当前 | 改为 |
|------|------|------|
| `<title>` | 糯米AI · 视频后期 · 智能转场/成片 | 糯米AI · ⑤ 智能转场 · Transition |
| `.work-head h1` | 视频后期 · 智能转场/成片 | ⑤ 智能转场 · Transition |
| 剧集 `<option>` | 第一集 · 成片 | 第1集 · 成片 |
| 剧集 `<option>` | 第二集 · 成片 | 第2集 · 成片 |

**标题渐变：** `.work-head h1` 加渐变（同 1）。

### 3. `web/dub-mode2.html` — ⑥ 配音 · DUBBING

| 位置 | 当前 | 改为 |
|------|------|------|
| `<title>` | 糯米AI · ⑤ 配音 · DUBBING | 糯米AI · ⑥ 配音 · DUBBING |
| `.work-head h1` | ⑤ 配音 · DUBBING | ⑥ 配音 · DUBBING |
| 集数 `<option>` | 第 1 集 | 第1集 |
| 集数 `<option>` | 第 2 集 | 第2集 |
| 集数 `<option>` | 第 3 集 | 第3集 |

**标题渐变：** `.work-head h1` 加渐变（同 1）。

### 4. `web/daw-soundtrack.html` — ⑦ 配乐 · Soundtrack

| 位置 | 当前 | 改为 |
|------|------|------|
| `<title>` | 糯米AI · ⑥ 视频后期 · 配乐 DAW… | 糯米AI · ⑦ 配乐 · Soundtrack |
| `.head h1` | ⑥ 视频后期 · 配乐 | ⑦ 配乐 · Soundtrack |

**标题渐变：已有，无需改 CSS。** 只改编号和文案。

---

## 统一渐变 CSS

三个壳内内容页 (`video-mode2.html`, `compose.html`, `dub-mode2.html`) 的 `.work-head h1` 都加上：

```css
.work-head h1 {
  margin: 0;
  font-size: 22px;
  background: linear-gradient(135deg, var(--blue), var(--mauve));
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
```

注意：需要分别确认三页原有 `font-size` 是否统一（当前 video-mode2: 21px, compose: 22px, dub-mode2: 22px），统一建议用 22px。

**h1 内嵌 span 处理：** `video-mode2.html` 的 h1 内 `<span id="taskTitle" style="color:var(--mauve);...">` 已有 inline color，不会被 `color: transparent` 覆盖。`dub-mode2.html` 无嵌套 span。`compose.html` 无嵌套 span。

---

## 集数写法规范

全部采用 `第N集` 格式（数字紧接"第"，无空格，如 `第1集`），替代 `第一集` / `第 1 集` 等不规范写法。

---

## 编号体系最终结果

| # | 页面 | 文件 | 标题 |
|---|------|------|------|
| ③ | 分镜板 | storyboard-board.html | ③ 分镜板 · STORYBOARD（不变） |
| ④ | 视频生成 | video-mode2.html | ④ 视频生成 · CLIPS |
| ⑤ | 智能转场 | compose.html | ⑤ 智能转场 · Transition |
| ⑥ | 配音 | dub-mode2.html | ⑥ 配音 · DUBBING |
| ⑦ | 配乐 | daw-soundtrack.html | ⑦ 配乐 · Soundtrack |

---

## 不动项

- 各面板除标题栏以外的功能区域
- JS 逻辑、API 调用、事件绑定
- 后端 Python 代码
- 分镜板 ③ 本身
- `tokens.css` 全局变量
