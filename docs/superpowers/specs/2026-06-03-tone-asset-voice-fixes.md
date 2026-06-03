# 六维定调面板 + 资源库出图 + 音色提示词自动加载 设计方案

> 设计日期: 2026-06-03 | 状态: 确认方向后设计

---

## 问题诊断与确认方向

### 问题 1: 「六维定调」面板颜色异常/白色块

**诊断**: `script.html` 的六维定调面板（第 211 行）使用 `background:var(--panel)`（正常），但内部 input / select 元素为浏览器默认样式。在 Windows 11 亮色主题的应用内 WebView 中，`<input>` / `<select>` 可能会应用系统主题（白色背景）而非页面定义的主题。

问题根源在于：`<input>` / `<select>` / `<textarea>` 元素**缺少显式的 `background` 和 `color` CSS 覆盖**（虽然 `#tonePanel` 使用 `var(--panel)`，但子元素 input/select 被系统样式覆盖）。

**相比其他面板**: 其他页面如 `ideate.html` 的 input 使用 `.field select, .field input { padding: 5px 8px; ... }` 做了全局重置，但 `script.html` 的六维定调面板在 `renderToneForm()`（第 727 行）通过 `valEl.style.cssText` 创建 input/select，**未指定 `background` 和 `color`**。

**修复方向**: 
1. 在 `renderToneForm()` 中给所有 input/select 强制加 `background:var(--field); color:var(--fg); border:1px solid var(--border);`
2. 可选：在 `tonePanel` 的 CSS 中添加子元素继承暗色主题（`#tonePanel input, #tonePanel select { background:var(--field); color:var(--fg); border:1px solid var(--border); }`）

### 问题 2: 资源库无法出图

**诊断**: 后端正道 `POST /assets/refs/generate` 已完整实现（`media_agent/routes/assets.py` 第 443-503 行），但前端 `web/asset-library.html` 没有调用该端点。没有任何生成按钮或触发逻辑。

资源库目前只负责**展示/编辑**由剧本页「规划实体」产出的 JSON 文件，缺少「生成参考图」这一步骤。

**修复方向**: 在资产库的三种实体卡片（角色/场景/道具）各添加「生成参考图」按钮 → 调用 `POST /assets/refs/generate`.

> 确认: 修复的目的是**允许用户在资源库生成参考图**——前端没调用后端 API，加按钮即可。不需要新建整个出图模式，资产库承载的是参考图生成+展示。

### 问题 3: 音色设计提示词无法自动加载

**诊断**: `dub-mode2.html` 依赖 `POST /audio_prompt` SSE 流式调用生成 `voices.json`，这是**用户主动触发**的（点击按钮），不是页面加载时自动执行。

如果用户之前已生成过音色设计（`voices.json` 已落盘），下次进入配音页时应能**自动加载**这些已有提示词。

**修复方向**: 页面初始化时，调用一个新端点（或现有的 `GET /project/files`）检查配音目录下是否存在 `voices.json`，若存在则加载并渲染到各镜头的音色提示词中。

---

## 改动方案

### 方案 1: 六维定调 input/select 颜色修复

**文件**: `web/script.html`

在 `renderToneForm()` 中，`valEl.style.cssText` 追加 `background:var(--field); color:var(--fg); border:1px solid var(--border);`

```javascript
// 每个 form 控件追加
valEl.style.cssText = "... background:var(--field); color:var(--fg); border:1px solid var(--border); border-radius:var(--radius-sm);";
noteEl.style.cssText = "... background:var(--field); color:var(--fg); border:1px solid var(--border); border-radius:var(--radius-sm);";
refEl.style.cssText = "... background:var(--field); color:var(--fg); border:1px solid var(--border); border-radius:var(--radius-sm);";
```

### 方案 2: 资产库「生成参考图」按钮

**文件**: `web/asset-library.html`

在 `renderGrid()` 中，每种实体卡片（角色/场景/道具）各加一个「生成参考图」按钮：

```html
<button class="iconb" data-act="gen-ref" data-name="${esc(e.name)}" data-kind="${key}">🖼 生成参考图</button>
```

在 `wireGrid()` 中添加对应的分发：

```javascript
if (act === "gen-ref") {
  genRef(kind, name);
  return;
}
```

实现 `genRef(kind, name)` 函数：

```javascript
async function genRef(kind, name) {
  if (!requireProject()) return;
  const el = REF_DATA[kind].entries.find(x => x.name === name);
  if (!el) { toast("实体不存在"); return; }
  // 从实体提取 prompt（角色取第一个变体，场景取第一个变体，道具取自身的 prompt）
  let prompt = "";
  if (kind === "characters") {
    const vars = el.variants || {};
    prompt = Object.values(vars)[0]?.prompt || "";
  } else if (kind === "scenes") {
    const vars = el.variants || {};
    prompt = Object.values(vars)[0]?.prompt || "";
  } else {
    prompt = el.prompt || "";
  }
  if (!prompt.trim()) { toast("请先在编辑器中填写该实体的出图提示词"); return; }
  toast("生成参考图中…");
  try {
    const r = await fetch(MEDIA_API + "/assets/refs/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project: PROJECT_DIR, kind, entity_id: name, prompt, size: curSize() }),
    });
    if (!r.ok) { toast("生成失败: " + ((await r.json().catch(() => null))?.detail || "HTTP " + r.status)); return; }
    const j = await r.json();
    toast(`已生成参考图: ${j.output}`);
    renderAll();  // 重新渲染以显示新生成的参考图
  } catch (e) { toast("生成失败: " + e.message); }
}
```

### 方案 3: 配音页自动加载已落盘的 voices.json

**文件**: `web/dub-mode2.html`

在页面初始化时（`loadEpisodeShots` 之后），尝试从配音目录读取已有 `voices.json`：

```javascript
// 尝试加载已落盘的 voices.json
async function autoLoadVoices() {
  if (!PROJECT_DIR) return;
  try {
    const files = await fetch(MEDIA_API + "/project/files?" 
      + new URLSearchParams({ project: PROJECT_DIR, sub: "dub", ext: "json" }));
    if (!files.ok) return;
    const j = await files.json();
    const fl = (j && j.files) || [];
    const voicesFile = fl.find(f => f.name === "voices.json");
    if (!voicesFile) return;
    const r = await fetch(MEDIA_API + "/file?path=" 
      + encodeURIComponent(voicesFile.path) + "&project=" + encodeURIComponent(PROJECT_DIR));
    if (!r.ok) return;
    const data = await r.json();
    if (data && data.voices) {
      _audioPromptCache = { ep: currentEpisodeId(), voices: data.voices, sfx: null, inflight: null };
      // 填充各镜头的音色提示词
      applyVoicesToShots(data.voices);
    }
  } catch (e) { /* 无文件则静默 */ }
}
```

---

## 改动涉及文件

| 文件 | 改动内容 |
|------|----------|
| `web/script.html` | 六维定调 panel input/select 强制暗色主题 |
| `web/asset-library.html` | 实体卡片添加「生成参考图」按钮 + `genRef()` 函数 |
| `web/dub-mode2.html` | 页面加载时自动检测并加载已有的 `voices.json` |

---

## 不动项

- 后端 API 不变
- token.css 全局变量不变
- 其他面板不变
