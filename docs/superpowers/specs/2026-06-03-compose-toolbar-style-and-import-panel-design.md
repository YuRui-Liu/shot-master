# 智能转场工具栏：样式修复 + 外部导入下拉面板

**日期**：2026-06-03  
**涉及文件**：`web/compose.html`

---

## 问题描述

1. **工具栏白色输入框**：`subDir` 和 `extDir` 两个 `<input>` 缺少 `type="text"` 属性，导致 `tokens.css` 的 `input[type="text"]` 选择器不匹配，浏览器使用白色默认样式，与深色主题格格不入。

2. **外部导入体验差**：工具栏上直接暴露一个原始文本框让用户手动输入绝对路径，无历史记录，操作繁琐。

---

## Fix 1：输入框样式修复

**根因**：`tokens.css:80` 选择器 `input[type="text"]` 只匹配显式写了 `type="text"` 的元素。两个工具栏 input 未写该属性。

**修复**：给 `subDir` input 添加 `type="text"` 属性（`extDir` 由 Fix 2 整体移除，无需单独处理）。无需改 CSS，tokens.css 样式自动生效（深色背景 `var(--field)` + 深色边框 `var(--border)`）。

---

## Fix 2：外部导入下拉面板

### 结构变更

- **移除**：工具栏中的 `extDir` 文本输入框（`<input id="extDir">`）
- **保留**：`＋ 外部导入` 按钮，改为触发下拉面板的开关
- **新增**：按钮正下方的绝对定位下拉面板

### 面板 HTML 结构

```
[＋ 外部导入 ▾]  ← 按钮，点击切换面板
│
└─ .ext-dropdown（绝对定位，z-index: 200）
   ├─ 最近使用（标题行）
   ├─ .ext-history-item × N（历史条目，最多5条）
   │   └─ 📁 路径文本 + ↵ 图标
   └─ 底部输入行
       ├─ <input type="text" id="extPathInput"> （路径输入框）
       └─ <button>导入</button>
```

### 交互规则

| 操作 | 行为 |
|------|------|
| 点击「＋ 外部导入」按钮 | 切换面板显示/隐藏 |
| 点击历史条目 | 将路径填入输入框，**不自动导入**（让用户确认） |
| 点击「导入」按钮 | 调用现有 `loadExternal(path)` 逻辑；成功后将路径写入历史、关闭面板 |
| 点击面板外区域 | 关闭面板（document click 监听，`e.target` 不在面板/按钮内则关闭） |
| 按 `Escape` | 关闭面板 |
| 导入失败 | toast 提示，面板保持打开，输入框保留路径供修改 |

### 历史记录存储

- **key**：`nuomi.extDirHistory.` + `encodeURIComponent(PROJECT)`（与其他本页 localStorage key 风格一致）
- **格式**：JSON 字符串数组，最新的排最前
- **上限**：5 条，超出时移除最旧的
- **写入时机**：导入成功后，将路径 unshift 到数组头部，去重（相同路径不重复）

### CSS

面板样式内联到 `compose.html` `<style>` 块（不污染全局），关键属性：

```css
.ext-dropdown {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  background: var(--panel);          /* #1e1f2e */
  border: 1px solid #3a3d5c;
  border-radius: 8px;
  width: 280px;
  box-shadow: 0 8px 28px rgba(0,0,0,.55);
  z-index: 200;
}
.ext-history-item {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 8px; border-radius: 5px; cursor: pointer;
  font-size: 11px; color: var(--muted);
}
.ext-history-item:hover { background: var(--panel2); }
```

按钮容器需 `position: relative` 以便下拉面板定位。

### 对现有代码的影响

- `loadExternal()` 函数：原来从 `document.getElementById("extDir").value` 读路径，改为接受参数 `loadExternal(path)`
- `wireToolbar()` 中 `addext` 的 case：由调用 `loadExternal()` 改为切换面板
- 移除 `extDir` 元素后，凡是引用 `document.getElementById("extDir")` 的地方需同步清理（当前只有 `loadExternal` 里一处）

---

## 实现范围

| 文件 | 改动 |
|------|------|
| `web/compose.html` | ① `subDir` / `extDir` input 加 `type="text"`；② 移除 `extDir` input；③ 新增下拉面板 HTML + CSS；④ `loadExternal` 改为接受 path 参数；⑤ 新增历史读写逻辑；⑥ `wireToolbar` 绑定开关逻辑 |

无需改动后端。
