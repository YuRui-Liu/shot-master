# 多页帮助文档 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把单文件帮助文档拆成一套面向最终用户的多页 HTML 文档（共享 CSS + 每页侧边导航 + Ctrl+F 检索 + 截图占位），符合桌面软件文档规范。

**Architecture:** 纯静态多页 HTML，全部在 `drama_shot_master/assets/help/` 下；共享一个 `assets/style.css`；每页内联同一段侧边导航 `<nav>`（当前页加 `active`）。零 JS、零构建，浏览器 `file://` 双击即开。软件菜单仍打开 `index.html`（不改代码）。

**Tech Stack:** HTML + CSS（无 JS / 无构建）。验证用 Python `html.parser`。

依据 spec：`docs/superpowers/specs/2026-05-26-help-docs-design.md`。

## 文件结构

```
drama_shot_master/assets/help/
  assets/style.css
  index.html  getting-started.html  activation.html
  image-split.html  image-combine.html  image-trim.html
  video.html  soundtrack.html  dubbing.html
  settings.html  custom-workflow.html
  faq.html  troubleshooting.html  glossary.html
```

## 通用约定（所有页面遵守）

1. 每页 `<head>` 引 `<link rel="stylesheet" href="assets/style.css">`，`<meta charset="UTF-8">`、`<meta name="viewport" ...>`、`<title>页名 · Drama-Shot-Master 帮助</title>`。
2. `<body>` 用统一骨架：`.layout` 包含 `.sidebar`（**完全相同**的导航块，仅当前页链接加 `class="active"`）与 `<main>`（面包屑 + h1 + 内容 + `.pager`）。
3. **侧边导航块（每页一字不差，只改 active）** —— 见 Task 1 的 `NAV_BLOCK`。新增页时复制它并把对应链接设 active。
4. 截图处用 `.shot` 占位框：`<figure class="shot"><span>图：<描述></span></figure>`（用户后续把 `<img src="assets/img/xxx.png">` 放进去）。
5. 内部链接用同目录相对路径（如 `href="video.html"`）。

## 复用验证脚本（每个建页任务末尾都跑一次）

把下面存为 `drama_shot_master/assets/help/_check.py`（**最后一个任务会删除它，不随包发布**）：

```python
"""校验 help/ 下所有页面：标签闭合、内部链接存在、引用了 style.css。"""
import sys
from pathlib import Path
from html.parser import HTMLParser

HELP = Path(__file__).resolve().parent
VOID = {"meta", "br", "img", "link", "input", "hr", "area", "base", "col", "source"}


class Bal(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.hrefs = []
        self.has_css = False

    def handle_starttag(self, t, attrs):
        d = dict(attrs)
        if t == "a" and d.get("href"):
            self.hrefs.append(d["href"])
        if t == "link" and d.get("href", "").endswith("style.css"):
            self.has_css = True
        if t not in VOID:
            self.stack.append(t)

    def handle_endtag(self, t):
        if self.stack and self.stack[-1] == t:
            self.stack.pop()
        elif t in self.stack:
            while self.stack and self.stack.pop() != t:
                pass


def main():
    pages = sorted(HELP.glob("*.html"))
    bad = []
    for p in pages:
        b = Bal()
        b.feed(p.read_text(encoding="utf-8"))
        if b.stack:
            bad.append(f"{p.name}: 标签未闭合 {b.stack[-5:]}")
        if not b.has_css:
            bad.append(f"{p.name}: 未引用 style.css")
        for h in b.hrefs:
            if h.startswith(("http", "#", "mailto:")):
                continue
            target = (HELP / h).resolve()
            if not target.exists():
                bad.append(f"{p.name}: 死链 -> {h}")
    if not (HELP / "assets" / "style.css").exists():
        bad.append("assets/style.css 缺失")
    if bad:
        print("FAIL:")
        for x in bad:
            print("  ", x)
        sys.exit(1)
    print(f"OK: {len(pages)} 页全部通过（标签闭合 / 引 CSS / 内链有效）")


if __name__ == "__main__":
    main()
```

运行：`python drama_shot_master/assets/help/_check.py`

---

### Task 1: 共享 CSS + 首页 index.html（奠定模板）

**Files:**
- Create: `drama_shot_master/assets/help/_check.py`（上面的校验脚本）
- Create: `drama_shot_master/assets/help/assets/style.css`
- Replace: `drama_shot_master/assets/help/index.html`（现有单页内容整体替换为新首页）

- [ ] **Step 1: 创建校验脚本**

把「复用验证脚本」一节的代码原样写入 `drama_shot_master/assets/help/_check.py`。

- [ ] **Step 2: 写 assets/style.css**

`drama_shot_master/assets/help/assets/style.css`：

```css
:root{
  --bg:#16172a; --panel:#1e2038; --ink:#e8e9f3; --muted:#9aa0c0;
  --accent:#6d5df6; --accent2:#3aa0ff; --line:#2c2e50; --code:#0f1020;
  --ok:#2BAA4A; --warn:#E0A33E; --err:#D9544D;
}
*{box-sizing:border-box;}
html{scroll-behavior:smooth;}
body{margin:0; font-family:"Segoe UI","Microsoft YaHei",system-ui,sans-serif;
  background:var(--bg); color:var(--ink); line-height:1.75;}
.layout{display:flex; min-height:100vh;}
.sidebar{width:248px; flex:0 0 248px; background:var(--panel);
  border-right:1px solid var(--line); position:sticky; top:0; height:100vh;
  overflow-y:auto; padding:22px 0;}
.sidebar .brand{padding:0 20px 4px; font-size:17px; font-weight:700;
  background:linear-gradient(90deg,var(--accent),var(--accent2));
  -webkit-background-clip:text; background-clip:text; color:transparent;}
.sidebar .brand small{display:block; color:var(--muted); font-size:12px;
  -webkit-text-fill-color:var(--muted); font-weight:400; margin-top:2px;}
.sidebar .group{padding:16px 20px 6px; color:#6b6f95; font-size:11px;
  letter-spacing:1px; text-transform:uppercase;}
.sidebar a{display:block; padding:8px 20px; color:var(--muted);
  text-decoration:none; border-left:3px solid transparent; font-size:14px;}
.sidebar a:hover{color:var(--ink); background:rgba(109,93,246,.10);}
.sidebar a.active{color:#fff; background:rgba(109,93,246,.16);
  border-left-color:var(--accent);}
main{flex:1; padding:34px 52px; max-width:900px;}
.breadcrumb{color:var(--muted); font-size:13px; margin-bottom:6px;}
.breadcrumb a{color:var(--muted); text-decoration:none;}
.breadcrumb a:hover{color:var(--ink);}
h1{font-size:27px; margin:4px 0 14px;}
h2{font-size:21px; margin:26px 0 10px; color:#fff;
  border-bottom:1px solid var(--line); padding-bottom:6px;}
h3{font-size:16px; margin:18px 0 6px; color:var(--accent2);}
p{margin:9px 0;}
.lead{color:var(--muted); font-size:15px;}
ul,ol{margin:9px 0; padding-left:24px;}
li{margin:5px 0;}
ol.steps{counter-reset:s; list-style:none; padding-left:0;}
ol.steps>li{counter-increment:s; position:relative; padding:4px 0 10px 38px; margin:0;}
ol.steps>li::before{content:counter(s); position:absolute; left:0; top:2px;
  width:26px; height:26px; border-radius:50%; background:var(--accent);
  color:#fff; text-align:center; line-height:26px; font-size:13px; font-weight:700;}
code{background:var(--code); padding:2px 6px; border-radius:4px;
  font-family:Consolas,Menlo,monospace; font-size:13px; color:#c9d1ff;}
.kbd{display:inline-block; background:#2a2c4e; border:1px solid var(--line);
  border-radius:4px; padding:1px 7px; font-size:12px;}
figure.shot{margin:10px 0; border:2px dashed var(--line); border-radius:8px;
  background:rgba(255,255,255,.02); min-height:120px; display:flex;
  align-items:center; justify-content:center;}
figure.shot span{color:var(--muted); font-size:13px;}
.note,.tip,.warn{padding:10px 14px; border-radius:6px; margin:12px 0; font-size:14px;}
.note{background:rgba(58,160,255,.08); border-left:3px solid var(--accent2); color:var(--muted);}
.tip{background:rgba(43,170,74,.08); border-left:3px solid var(--ok); color:var(--muted);}
.warn{background:rgba(224,163,62,.10); border-left:3px solid var(--warn); color:#e9d9bd;}
table.params{border-collapse:collapse; width:100%; margin:12px 0; font-size:14px;}
table.params th,table.params td{border:1px solid var(--line); padding:8px 10px; text-align:left;}
table.params th{background:rgba(109,93,246,.12); color:#fff;}
.cards{display:flex; flex-wrap:wrap; gap:14px; margin:14px 0;}
.cards a{flex:1 1 200px; background:var(--panel); border:1px solid var(--line);
  border-radius:10px; padding:14px 16px; text-decoration:none; color:var(--ink);}
.cards a:hover{border-color:var(--accent);}
.cards a b{color:#fff;} .cards a span{display:block; color:var(--muted); font-size:13px; margin-top:4px;}
.pager{display:flex; justify-content:space-between; margin-top:36px;
  border-top:1px solid var(--line); padding-top:14px; font-size:14px;}
.pager a{color:var(--accent2); text-decoration:none;}
.pager .none{color:transparent;}
footer{color:#5a5e85; font-size:12px; margin-top:24px;}
@media (max-width:760px){
  .layout{flex-direction:column;} .sidebar{width:auto; flex:none; height:auto; position:static;}
  main{padding:20px;}
}
```

- [ ] **Step 3: 定义并写入 NAV_BLOCK（首页版，active 在「软件简介」）**

下面这段 `<nav>` 是**所有页面共用**的（建其它页时复制，改 active）。在 index.html 中，`index.html` 链接加 `class="active"`：

```html
    <nav class="sidebar">
      <div class="brand">Drama-Shot-Master<small>用户帮助文档</small></div>
      <div class="group">入门</div>
      <a href="index.html">软件简介</a>
      <a href="getting-started.html">快速开始</a>
      <a href="activation.html">激活与授权</a>
      <div class="group">功能详解</div>
      <a href="image-split.html">拆图</a>
      <a href="image-combine.html">拼图</a>
      <a href="image-trim.html">去白边</a>
      <a href="video.html">视频生成</a>
      <a href="soundtrack.html">配乐</a>
      <a href="dubbing.html">配音</a>
      <div class="group">配置与进阶</div>
      <a href="settings.html">设置说明</a>
      <a href="custom-workflow.html">自定义工作流</a>
      <div class="group">支持</div>
      <a href="faq.html">常见问题</a>
      <a href="troubleshooting.html">故障排查</a>
      <a href="glossary.html">术语表</a>
    </nav>
```

- [ ] **Step 4: 写 index.html（首页）**

整体替换 `drama_shot_master/assets/help/index.html` 为：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>软件简介 · Drama-Shot-Master 帮助</title>
<link rel="stylesheet" href="assets/style.css">
</head>
<body>
<div class="layout">
    <!-- NAV_BLOCK，active = index.html -->
    <nav class="sidebar">
      <div class="brand">Drama-Shot-Master<small>用户帮助文档</small></div>
      <div class="group">入门</div>
      <a href="index.html" class="active">软件简介</a>
      <a href="getting-started.html">快速开始</a>
      <a href="activation.html">激活与授权</a>
      <div class="group">功能详解</div>
      <a href="image-split.html">拆图</a>
      <a href="image-combine.html">拼图</a>
      <a href="image-trim.html">去白边</a>
      <a href="video.html">视频生成</a>
      <a href="soundtrack.html">配乐</a>
      <a href="dubbing.html">配音</a>
      <div class="group">配置与进阶</div>
      <a href="settings.html">设置说明</a>
      <a href="custom-workflow.html">自定义工作流</a>
      <div class="group">支持</div>
      <a href="faq.html">常见问题</a>
      <a href="troubleshooting.html">故障排查</a>
      <a href="glossary.html">术语表</a>
    </nav>
  <main>
    <div class="breadcrumb">首页</div>
    <h1>Drama-Shot-Master 用户帮助</h1>
    <p class="lead">面向短剧分镜的桌面工作台：从分镜图的图像处理（拆图 / 拼图 / 去白边），
      到基于 LTX 2.3 的视频生成、配乐与配音，一站式完成"分镜图 → 成片"。</p>

    <h2>它能做什么</h2>
    <div class="cards">
      <a href="image-split.html"><b>拆图 / 拼图 / 去白边</b><span>分镜大图切分、多图拼接、去除白边</span></a>
      <a href="video.html"><b>视频生成</b><span>分镜 + 提示词生成视频，多任务并行</span></a>
      <a href="soundtrack.html"><b>配乐</b><span>自动卡点分析与配乐对齐</span></a>
      <a href="dubbing.html"><b>配音</b><span>音色设计 / 情感声音克隆</span></a>
    </div>

    <h2>界面布局</h2>
    <p>主窗口分三栏：左栏管理"当前目录 / 输出目录"，中栏是缩略图，右栏是当前功能的参数面板。
      顶部一行功能切换条按"图像 / 视频"分组。视频生成 / 配乐 / 配音为独占主区的任务式面板。</p>
    <figure class="shot"><span>图：主界面三栏布局</span></figure>

    <h2>从这里开始</h2>
    <ol class="steps">
      <li>先看 <a href="getting-started.html">快速开始</a>，5 步跑通第一次操作。</li>
      <li>首次使用需 <a href="activation.html">激活</a>。</li>
      <li>按需查阅各功能页与 <a href="faq.html">常见问题</a>。</li>
    </ol>

    <div class="pager"><span class="none">·</span><a href="getting-started.html">下一页：快速开始 →</a></div>
    <footer>© 2026 二进制糯米 · Drama-Shot-Master 帮助文档</footer>
  </main>
</div>
</body>
</html>
```

- [ ] **Step 5: 校验**

Run: `python drama_shot_master/assets/help/_check.py`
Expected: 因其它页还没建，会报死链（getting-started.html 等不存在）——**本步只确认 index.html 自身标签闭合且引用了 css**；可临时只看 index：
`QT_QPA_PLATFORM= python -c "from html.parser import HTMLParser"` 不需要。改为：先跳过死链，确认无"标签未闭合/未引用 css"。完成全部页后（Task 7）再要求 `_check.py` 全绿。

> 执行提示：Task 1–6 期间 `_check.py` 会因未建页面报死链，属正常；每个任务只需确认**本任务新建/修改页**自身标签闭合、引 css。Task 7 才要求全绿。

- [ ] **Step 6: 提交**

```bash
git add drama_shot_master/assets/help/_check.py drama_shot_master/assets/help/assets/style.css drama_shot_master/assets/help/index.html
git commit -m "docs(help): 多页文档骨架 — 共享 style.css + 首页 index.html + 校验脚本"
```

---

### Task 2: 入门组 — getting-started.html + activation.html

**Files:**
- Create: `drama_shot_master/assets/help/getting-started.html`
- Create: `drama_shot_master/assets/help/activation.html`

每页用 Task 1 的页骨架（同 `<head>` 写法 + 复制 NAV_BLOCK 并把对应链接设 active + `<main>` 内面包屑/h1/内容/pager/footer）。下面给出各页 **`<main>` 内容**与 nav/breadcrumb/pager 取值；实现时套用骨架写成完整 HTML。

- [ ] **Step 1: 写 getting-started.html**

nav active = `getting-started.html`；breadcrumb = `<a href="index.html">首页</a> / 入门 / 快速开始`；pager = 上一页 index.html(软件简介)、下一页 activation.html(激活与授权)。`<title>快速开始 · …`。

`<main>` 内容（写成对应 HTML 标签）：
- h1：快速开始
- h2 系统要求：Windows 10/11 64 位；需 RunningHub 账号与 API Key（视频/配音/配乐用到）；生成类功能需联网；图像处理（拆图/拼图/去白边）本地即可、无需联网。
- h2 安装与启动：解压发行包 → 运行主程序 exe → 首次启动需激活（见激活页）。用 `.note` 提示"杀软误报见故障排查"。
- h2 五步跑通（`ol.steps`）：① 左栏「打开目录」选分镜所在文件夹；② 「设置输出目录」选导出位置；③ 顶部选功能（如"拆图"）；④ 右栏填参数、中栏选图；⑤ 点「执行」（视频/配音/配乐则在任务窗点「生成」）。每步可配 `figure.shot` 占位。
- h2 提示（`.tip`）：缩略图大小可调；多选支持 Ctrl/Shift。

- [ ] **Step 2: 写 activation.html**

nav active = `activation.html`；breadcrumb = 首页 / 入门 / 激活与授权；pager = 上一页 getting-started.html、下一页 image-split.html(拆图)。

`<main>` 内容：
- h1：激活与授权
- p(lead)：软件需激活后使用，首次启动会要求输入激活码。
- h2 激活步骤（`ol.steps`）：① 打开「关于」对话框，复制本机**机器码**；② 把机器码发给作者（邮箱见下）；③ 收到与该机器绑定、带有效期的**激活码**；④ 把激活码粘进「关于」输入框点「激活」。配 shot 占位。
- h2 续期与到期：`.note` 说明到期前 7 天会提醒；过期后需重新激活。激活码**与本机绑定**，换电脑需重新申请。
- h2 联系作者：作者「二进制糯米」，邮箱 `1062283553@qq.com`。
- h2 常见激活问题：列 2–3 条（提示"激活码非本机"=机器码不匹配；"激活码无效"=复制不全/有空格）。

- [ ] **Step 3: 校验本任务两页**

Run: `python drama_shot_master/assets/help/_check.py`
Expected: 死链仍可能存在（未建页面），但 getting-started.html / activation.html 不应报"标签未闭合/未引用 css"。

- [ ] **Step 4: 提交**

```bash
git add drama_shot_master/assets/help/getting-started.html drama_shot_master/assets/help/activation.html
git commit -m "docs(help): 入门组 — 快速开始 + 激活与授权"
```

---

### Task 3: 图像功能三页 — 拆图 / 拼图 / 去白边

**Files:**
- Create: `image-split.html`, `image-combine.html`, `image-trim.html`（均在 `drama_shot_master/assets/help/`）

三页都用**功能页统一骨架**（spec）：概述 → 适用场景 → 操作步骤 → 参数说明(表) → 提示与技巧 → 常见问题。套 Task 1 页骨架。

- [ ] **Step 1: image-split.html（拆图）**

nav active=image-split；breadcrumb=首页 / 功能详解 / 拆图；pager 上=activation.html 下=image-combine.html。内容：
- 概述：把一张网格大图（如 2×2、4×4 分镜）自动切成多张子图。
- 适用场景：AI 出的多格分镜大图需拆成单张。
- 操作步骤(steps)：选目录→选「拆图」→填源网格/子图行列→（可「一键检测」白边/网格自动填）→选图→「执行」。配 shot。
- 参数说明(table.params)：源行/列、子行/列、白边阈值、最大迭代、命名后缀、格式、重采样(Lanczos/AI) —— 每行含义。
- 提示：白带检测对不均匀间距鲁棒；可选 AI 放大。
- 常见问题：拆出有白边？→ 配合去白边；格子检测不准？→ 手填行列。

- [ ] **Step 2: image-combine.html（拼图）**

nav active=image-combine；breadcrumb 末=拼图；pager 上=image-split 下=image-trim。内容：
- 概述：多图按 R×C 网格拼成一张大图。
- 操作步骤：选「拼图」→order 模式逐个点选定序（<span class="kbd">Shift</span> 区间选按行序追加）→设行列/间距/比例/缩放→「执行」。
- 参数说明(table)：目标行列、间距 gap、目标比例、缩放方式(留边/裁切/拉伸)、背景色。
- 提示：缩放方式区别；Shift 区间选。
- 常见问题：顺序错了？→ 再点取消重选；比例留边发虚？→ 改裁切。

- [ ] **Step 3: image-trim.html（去白边）**

nav active=image-trim；breadcrumb 末=去白边；pager 上=image-combine 下=video。内容：
- 概述：自动迭代裁掉图片四周残留白边。
- 操作步骤：选「去白边」→设阈值/最大迭代→（白边去不净时设"额外向内裁剪 上/下/左/右"）→选图（Ctrl/Shift 多选）→「执行」。
- 参数说明(table)：阈值、最大迭代、额外向内裁剪四向、命名后缀、格式。
- 提示(.tip)：非均匀白框用"额外向内裁剪"微调（防止生成视频带白边）。
- 常见问题：白边没去净？→ 调阈值或用向内裁剪；裁过头？→ 减小向内裁剪。

- [ ] **Step 4: 校验 + 提交**

Run: `python drama_shot_master/assets/help/_check.py`（确认三页自身闭合/引 css）

```bash
git add drama_shot_master/assets/help/image-split.html drama_shot_master/assets/help/image-combine.html drama_shot_master/assets/help/image-trim.html
git commit -m "docs(help): 功能详解 — 拆图/拼图/去白边"
```

---

### Task 4: 视频组三页 — 视频生成 / 配乐 / 配音

**Files:**
- Create: `video.html`, `soundtrack.html`, `dubbing.html`

同功能页骨架。

- [ ] **Step 1: video.html（视频生成）**

nav active=video；breadcrumb 末=视频生成；pager 上=image-trim 下=soundtrack。内容：
- 概述：基于 LTX 2.3 导演台工作流，从分镜图 + 提示词生成视频。
- 适用场景：把分镜图变成带运镜的视频片段。
- 操作步骤(steps)：选「视频生成」→「新建」任务（独立窗）→拖分镜到时间轴→分段写提示词（运镜/画面/音效）→选工作流（导演台 / ALL IN ONE V3）→「生成」→完成后预览。多个任务可并行、各自独立窗口，不满意回到对应窗重生成。配 shot。
- 参数说明(table)：全局提示词、时长/帧、分段长度、引导强度、是否自定义音频、工作流选择。
- 提示(.note)：提交前需在「设置→RunningHub 配置」填 API Key 与各工作流 workflow_id。
- 常见问题：生成不遵循图/分辨率不对？→ 见故障排查；要换自己的工作流？→ 见自定义工作流。

- [ ] **Step 2: soundtrack.html（配乐）**

nav active=soundtrack；breadcrumb 末=配乐；pager 上=video 下=dubbing。内容：
- 概述：为成片自动分析卡点并生成/对齐配乐，独立任务窗管理。
- 操作步骤：选「配乐」→新建任务→选视频→分析卡点（卡点编辑器可微调）→生成/对齐→导出。配 shot。
- 参数说明(table)：风格、随机种子、交叉淡入淡出、卡点参数等（在「设置→配乐…」）。
- 提示：卡点编辑器可手动增删卡点。
- 常见问题：卡点太多/太少？→ 调灵敏度/最大数量。

- [ ] **Step 3: dubbing.html（配音）**

nav active=dubbing；breadcrumb 末=配音；pager 上=soundtrack 下=settings。内容：
- 概述：基于 RunningHub TTS 工作流为台词配音，独立任务窗。顶部切换两种方式。
- 操作步骤(steps)：选「配音」→新建任务→任务窗顶部选「音色设计」或「声音克隆」→填表单→「生成」→「打开结果」试听 FLAC。
- h3 音色设计：填 要合成文本 / 音色描述(自然语言) / 语言。
- h3 声音克隆：填 文本 / 说话人参考音频 / 情感强度；并选 4 种情感模式之一：默认(随参考音频) / 文本情绪(写情感描述) / 语音情绪模仿(传情感参考音频) / 情感向量(8 维 Happy/Angry/Sad/Fear/Hate/Low/Surprise/Neutral)。配 shot。
- 参数说明(table)：情感强度 emo_alpha(0–2)、各情感模式所需输入。
- 提示(.note)：在「设置→配音…」配两个工作流 ID 与输出目录。
- 常见问题：模式 3 不可用？→ 需线上工作流含情感音频输入（见自定义工作流）。

- [ ] **Step 4: 校验 + 提交**

Run: `python drama_shot_master/assets/help/_check.py`

```bash
git add drama_shot_master/assets/help/video.html drama_shot_master/assets/help/soundtrack.html drama_shot_master/assets/help/dubbing.html
git commit -m "docs(help): 功能详解 — 视频生成/配乐/配音"
```

---

### Task 5: 配置与进阶 — 设置说明 + 自定义工作流

**Files:**
- Create: `settings.html`
- Create: `custom-workflow.html`

- [ ] **Step 1: settings.html（设置说明）**

nav active=settings；breadcrumb=首页 / 配置与进阶 / 设置说明；pager 上=dubbing 下=custom-workflow。内容：
- 概述：菜单「设置」下各配置对话框的字段含义。
- h3 RunningHub 配置：API Key、Base URL、视频输出目录、各工作流 workflow_id、自定义模板路径。
- h3 翻译配置：（DeepLX / 服务地址等，按实际字段）。
- h3 提示词优化配置：meta-prompt 路径、provider(base_url/key/model，Ollama/豆包)。
- h3 配乐：风格/种子/交叉淡化等。
- h3 配音：音色设计 / 声音克隆 两个 workflow_id、输出目录。
- 用 `table.params` 列字段。`.note` 提示节点号高级覆盖在 `settings.json` 的 `dub_node_profiles`（详见自定义工作流）。

- [ ] **Step 2: custom-workflow.html（自定义工作流）**

nav active=custom-workflow；breadcrumb 末=自定义工作流；pager 上=settings 下=faq。**迁移现有内容**：把当前 `index.html`（被 Task 1 替换前的旧版）里"高级·自定义工作流"那一节的三层内容搬过来并适配新样式（h2/h3 + ol/ul + .note）：
- 概念：软件提交到 RunningHub 已保存工作流(workflow_id) + 节点参数覆盖。
- 一、换用自己的工作流（免改代码）：部署→复制 workflow_id→视频在「RunningHub 配置」填、配音在「配音…」填；可设自定义模板路径。
- 二、节点号不一致：改 `settings.json` 的 `dub_node_profiles` 覆盖"角色→节点号"（列声音克隆默认 4/10/16/19/21/26/1/14/17/20）；提示用 API 格式导出对照。
- 三、新增工作流类型（开发者向，一句带过）：`workflow_profiles.py` / `tts_profiles.py` 加 profile。
- `.note`：软件只覆盖 widget/开关，不改工作流图；多分支靠覆盖选组开关。

> 注：旧版 index.html 里"自定义工作流"那节的成稿可从 git 历史取回复用——
> `git log --oneline -- drama_shot_master/assets/help/index.html` 找到含该节的提交（提交信息含"自定义工作流"），
> `git show <sha>:drama_shot_master/assets/help/index.html` 取出原 HTML，把 `#custom-workflow` 那段 `<section>` 内容搬进新页并适配新样式（h2/h3/ol/ul/.note）。省得重写。

- [ ] **Step 3: 校验 + 提交**

Run: `python drama_shot_master/assets/help/_check.py`

```bash
git add drama_shot_master/assets/help/settings.html drama_shot_master/assets/help/custom-workflow.html
git commit -m "docs(help): 配置与进阶 — 设置说明 + 自定义工作流"
```

---

### Task 6: 支持组 — 常见问题 / 故障排查 / 术语表

**Files:**
- Create: `faq.html`, `troubleshooting.html`, `glossary.html`

- [ ] **Step 1: faq.html（常见问题）**

nav active=faq；breadcrumb=首页 / 支持 / 常见问题；pager 上=custom-workflow 下=troubleshooting。内容：用 h3 问 + p 答，覆盖：
- 如何获取 RunningHub API Key？（去 RunningHub 账户获取，填进设置）
- 生成一个视频/配音要多久？（取决于云端排队与时长，可在任务窗看状态）
- 输出文件在哪？（在设置的输出目录下，视频 / 配音(FLAC) / 配乐分子目录）
- 图像处理要联网吗？（不需要；视频/配音/配乐需要）
- 能同时跑多个任务吗？（能，各任务独立窗口并行）

- [ ] **Step 2: troubleshooting.html（故障排查）**

nav active=troubleshooting；breadcrumb 末=故障排查；pager 上=faq 下=glossary。内容：问题→原因→解决，用 h3 + ul：
- 「ComfyUI / RunningHub 不可达」：检查网络、API Key、Base URL。
- 生成失败 / 报错：看任务窗状态与提示；确认 workflow_id 正确、素材已上传。
- 视频"不遵循图 / 分辨率错"：确认用对工作流；参考自定义工作流的节点映射。
- 激活失败：机器码非本机 / 激活码复制不全。
- 启动被杀软拦截（打包后）：原生编译的误报，加信任或用已签名版本。
- 找不到输出：确认已设输出目录。
用 `.warn` 标注重要项。

- [ ] **Step 3: glossary.html（术语表）**

nav active=glossary；breadcrumb 末=术语表；pager 上=troubleshooting 下=（无，pager 右用 `<span class="none">`）。内容：`<dl>` 或 h3+p 列：分镜、工作流、workflow_id、节点(node)、nodeInfoList、LTX 2.3、TTS、音色设计、声音克隆、机器码、激活码、卡点。每条一句话解释。

- [ ] **Step 4: 校验 + 提交**

Run: `python drama_shot_master/assets/help/_check.py`

```bash
git add drama_shot_master/assets/help/faq.html drama_shot_master/assets/help/troubleshooting.html drama_shot_master/assets/help/glossary.html
git commit -m "docs(help): 支持组 — 常见问题/故障排查/术语表"
```

---

### Task 7: 全量校验 + 清理

**Files:**
- Delete: `drama_shot_master/assets/help/_check.py`（验证脚本不随包发布）

- [ ] **Step 1: 全量结构校验（所有页都已存在，应全绿）**

Run: `python drama_shot_master/assets/help/_check.py`
Expected: `OK: 14 页全部通过（标签闭合 / 引 CSS / 内链有效）`
（若报死链或未闭合，回到对应页修正后重跑，直到全绿。）

- [ ] **Step 2: 校验侧边导航在所有页一致**

Run:
```bash
cd drama_shot_master/assets/help && python -c "
import re,glob
def nav(f):
    s=open(f,encoding='utf-8').read()
    m=re.search(r'<nav class=\"sidebar\">(.*?)</nav>',s,re.S).group(1)
    return re.sub(r'\sclass=\"active\"','',m).split()
base=nav('index.html')
bad=[f for f in glob.glob('*.html') if nav(f)!=base]
print('导航不一致的页:', bad or '无（全部一致）')
"
```
Expected: `无（全部一致）`（去掉 active 后每页导航块应完全相同）。

- [ ] **Step 3: 人工验证（手动）**

浏览器打开 `drama_shot_master/assets/help/index.html`：逐页点侧栏与「上一页/下一页」，确认样式、跳转、面包屑正确；从软件「关于→帮助文档」打开确认入口正常。

- [ ] **Step 4: 删除校验脚本 + 提交**

```bash
git rm drama_shot_master/assets/help/_check.py
git commit -m "docs(help): 全量校验通过，移除临时校验脚本"
```

---

## Self-Review

**Spec 覆盖**：
- 多页 HTML + 共享 CSS → Task 1（style.css）+ 各页。✅
- 每页侧边导航(分组+active) + 面包屑 + 上一页/下一页 → Task 1 NAV_BLOCK + 各页骨架；Task 7 校验导航一致。✅
- 截图占位 `.shot` → CSS + 各功能页步骤处。✅
- 14 页清单（入门3/功能6/进阶2/支持3）→ Task 2–6 全覆盖。✅
- 功能页统一结构（概述/场景/步骤/参数/提示/FAQ）→ Task 3/4 明确按此。✅
- 各页要点（依据软件实际功能）→ Task 2–6 逐页列出，与 spec 一致。✅
- App 集成不改代码（菜单打开 index.html）→ Task 1 替换 index.html，路径相对同级。✅
- 验证（标签闭合/内链/css 路径）→ `_check.py` + Task 7 全量。✅
- 打包随发布 → 文件都在 `assets/help/`（已在 Nuitka include-data-dir）；`_check.py` Task 7 删除不发布。✅

**占位扫描**：截图占位是 spec 要求的内容（非计划占位）。Task 2–6 给的是"每页 main 内容要点 + nav/breadcrumb/pager 取值 + 套 Task 1 骨架"——属内容创作大纲（文档类不可能在 plan 里逐字预写全部 14 页散文，故给精确小节结构 + 要点 + 一份完整范例 index.html 作样板）；执行者据此 + 参照 index.html 写成完整 HTML。无 TBD/「稍后补」。

**一致性**：所有页共用同一 `assets/style.css` 与同一 NAV_BLOCK（Task 7 脚本强制校验一致）；CSS class 名（.sidebar/.steps/.shot/.note/.tip/.warn/.params/.cards/.pager/.kbd）在 CSS 与各页用法一致；pager 链接构成首尾相连的线性序：index→getting-started→activation→image-split→image-combine→image-trim→video→soundtrack→dubbing→settings→custom-workflow→faq→troubleshooting→glossary（首页无上一页、术语表无下一页，用 `.none` 占位）。✅

**给执行者提醒**：每建一页都从 Task 1 的 index.html 复制整段骨架（head + NAV_BLOCK + main 外壳），仅改 `<title>`、active 链接、面包屑、pager 与 main 内容，确保导航块逐字一致（Task 7 会校验）。
