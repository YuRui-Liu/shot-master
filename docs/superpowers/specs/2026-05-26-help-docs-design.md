# 帮助文档系统（多页 HTML）— 设计

**日期**：2026-05-26
**目标**：把单文件 `help/index.html` 拆成一套**多页 HTML 帮助文档**，面向**购买软件的最终用户**，指导其了解软件、掌握各功能用法；符合桌面软件文档规范；便于后续扩展与按页检索。
**受众**：购买/使用软件的普通用户（不是开发者）。内容不暴露源码细节；`custom-workflow.html` 面向进阶用户讲"接入自己的 RunningHub 工作流"。

## 关键约束与已确认决策

- 软件经「关于→帮助文档」用 **OS 浏览器以本地 `file://`** 打开 `help/index.html`（`main_window.py:_open_help`，不改）。
- **多页 HTML + 共享外部 CSS**（零依赖、双击即开、离线可用）。不用 Markdown/构建/JS 渲染（file:// 下 fetch .md 会被 CORS 拦）。
- **检索 = 每页常驻侧边目录 + 浏览器 Ctrl+F**（零 JS、零维护）。
- **截图占位**：步骤处放带标题的占位框，用户后续放图并改 `img` 路径。

## 文件结构

```
drama_shot_master/assets/help/
  assets/style.css          # 共享样式（从现 index.html 内联样式抽出 + 扩展组件）
  index.html                # 首页/概述（菜单打开这个）
  getting-started.html      # 快速开始（含系统要求 / 安装）
  activation.html           # 激活与授权
  image-split.html          # 拆图
  image-combine.html        # 拼图
  image-trim.html           # 去白边
  video.html                # 视频生成
  soundtrack.html           # 配乐
  dubbing.html              # 配音
  settings.html             # 设置总览
  custom-workflow.html      # 自定义工作流（进阶）
  faq.html                  # 常见问题
  troubleshooting.html      # 故障排查
  glossary.html             # 术语表
```
共 1 个 CSS + 14 个页面。`help/assets/` 与 `help/` 均在 Nuitka 打包的 `--include-data-dir=drama_shot_master/assets` 范围内，随包发布。

## 共享页面模板（每页一致，符合规范）

每个 HTML 页面结构：
```
<head> 链接 assets/style.css（所有页面都直接在 help/ 下，路径统一 assets/style.css）</head>
<body>
  <div class="layout">
    <nav class="sidebar">
      品牌(产品名+「帮助文档」) + 分组导航（见下），当前页 <a class="active">
    </nav>
    <main>
      <div class="breadcrumb">首页 / 分组 / 当前页</div>
      <h1>页标题</h1>
      ……正文（用共享组件）……
      <div class="pager"><a 上一页> <a 下一页></div>
    </main>
  </div>
</body>
```

**侧边导航分组（每页相同）**：
- 入门：首页 / 快速开始 / 激活与授权
- 功能详解：拆图 / 拼图 / 去白边 / 视频生成 / 配乐 / 配音
- 配置与进阶：设置说明 / 自定义工作流
- 支持：常见问题 / 故障排查 / 术语表

## CSS 组件（style.css 提供，复用现有深色主题 + 紫蓝点缀）

沿用现 index.html 的配色变量与暗色风格，外置为 `style.css`，并新增：
- `.sidebar`（固定左栏，分组标题 `.group`，链接 `a` / 当前 `a.active`）。
- `.breadcrumb`（面包屑，次要色）。
- `.steps`（有序步骤，编号醒目）。
- `.shot`（截图占位框：虚线边框 + 居中标题文字，如「图：视频生成任务窗」；含可替换的 `<img>` 注释示例）。
- `.note` / `.tip` / `.warn`（信息/技巧/警告 callout，左色条）。
- `.params`（参数说明表格样式）。
- `.kbd`（键盘键）、`code`（行内代码）。
- `.pager`（上一页/下一页）。
- 响应式：窄屏侧栏可折到顶部（简单 media query，非必须强求）。

## 功能页统一内容结构

`image-split / image-combine / image-trim / video / soundtrack / dubbing` 六页都按同一骨架写：
1. **概述**：这个功能做什么，一句话价值。
2. **适用场景**：什么时候用它。
3. **操作步骤**：编号步骤 + 截图占位（关键步骤各一个占位框）。
4. **参数说明**：表格列出界面上的可调项及含义/默认值。
5. **提示与技巧**：实用建议（如去白边的「额外向内裁剪」、拼图 Shift 区间选、视频多任务并行）。
6. **常见问题**：该功能 2–4 条 FAQ。

各页要点（内容依据软件实际功能，准确不杜撰）：
- **拆图**：网格大图→子图；白带检测；一键检测白边/网格；可选重采样(Lanczos/AI)。
- **拼图**：多图按 R×C 拼接；order 模式点选定序，Shift 区间选按行序追加；目标比例/间距/缩放方式。
- **去白边**：迭代裁白边；阈值/最大迭代；额外向内裁剪(上下左右)；Ctrl/ Shift 多选。
- **视频生成**：LTX 2.3 导演台；分镜+分段提示词(运镜/画面/音效)；多任务独立窗并行；导演台/ALL IN ONE V3 切换；需先配 RunningHub。
- **配乐**：自动卡点分析+配乐对齐；卡点编辑器；独立任务窗；设置→配乐。
- **配音**：音色设计(文本/音色描述/语言) 与 声音克隆(文本/参考音频/情感强度 + 4 情感模式：默认/文本情绪/语音情绪模仿/情感向量) 顶部切换；独立任务窗；设置→配音。

## 其它页要点

- **首页 index.html**：产品定位（短剧分镜工作台）、功能总览（带卡片/链接跳各功能页）、三步上手指引、版本与版权（二进制糯米）。
- **快速开始**：系统要求（Windows、需 RunningHub 账号与 API Key、联网）、安装/启动、首跑 5 步（打开目录→设输出目录→选功能→操作→出结果）。
- **激活与授权**：机器码→把机器码发作者→收激活码→「关于」粘贴激活；机器绑定、到期续期；常见激活问题。
- **设置说明**：逐项解释 RunningHub 配置 / 翻译配置 / 提示词优化配置 / 配乐 / 配音 各对话框的字段。
- **自定义工作流**：沿用并扩展现有"接入 RunningHub 工作流"三层内容（换 workflow_id / 节点号覆盖 / 新增 profile 一句带过）。
- **常见问题**：跨功能高频问题（如何拿 API Key、生成要多久、输出在哪、能离线吗）。
- **故障排查**：ComfyUI/ RunningHub 不可达、生成失败、激活失败、杀软误报（打包后）、找不到输出文件。
- **术语表**：分镜、工作流、workflow_id、节点(node)、nodeInfoList、LTX、TTS、音色设计、声音克隆、机器码、激活码。

## App 集成

不改 `main_window.py`：`_open_help` 仍打开 `assets/help/index.html`；index.html 升级为带侧栏导航的首页，其余页通过侧栏互链。相对链接以 `index.html` 同级为基准（`href="video.html"`、CSS `href="assets/style.css"`）。

## 落地顺序（plan 阶段细化）

1. 抽出/编写 `assets/style.css` + 定义页面模板与所有 CSS 组件。
2. 写「首页 + 侧边导航」骨架（导航在所有页一致，先在 index 定稿再复制到各页）。
3. 入门组三页（快速开始/激活）。
4. 功能详解六页（按统一骨架）。
5. 配置与进阶两页（设置说明/自定义工作流，后者迁移现有内容）。
6. 支持三页（FAQ/故障排查/术语表）。
7. 校验：所有页 HTML 闭合平衡、内部链接互通、CSS 路径正确、菜单打开 index 正常跳转。

## 验证

- 结构校验：每个 HTML 用 `html.parser` 检查标签闭合；所有 `href` 指向存在的同目录文件；`assets/style.css` 路径正确。
- 人工：浏览器打开 index.html，逐页点侧栏导航与上一页/下一页，确认样式/跳转正常；从软件「关于→帮助文档」打开验证。

## 非目标

- 不引入构建步骤 / JS 框架 / 全文搜索引擎。
- 不写开发者 API/源码级文档（仅 custom-workflow 进阶一节面向高级用户）。
- 不内嵌真实截图（留占位，用户后补）。
- 不做多语言（仅中文）。
