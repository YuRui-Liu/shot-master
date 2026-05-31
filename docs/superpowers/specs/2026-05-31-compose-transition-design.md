# 成片合成 · 转场智能体（Compose / AutoTransition）设计规范

**日期**：2026-05-31
**状态**：已确认，待实施
**UI 参考图**：`docs/explorer/成片合成-layout.html`（高保真布局已用户拍板）
**前置调研**：`docs/explorer/自动转场智能体.md`（豆包初稿，4 层架构思路）；本规范是其在本项目落地的收敛版

---

## 1. 概述与目标

视频生成（`video_gen` / RunningHub）产出**若干 mp4 片段**：每段内含 1–3 个分镜、**段内转场已完成**，但**段与段之间还没有转场**。本功能在「视频后期」新增「**成片**」阶段，提供：

1. **快速看片剔除**：人工看片，保留/剔除片段、拖拽排序、单片段头尾 trim。
2. **一键转场智能体**：对保留片段做 CV 分析，自动为每个切口选转场效果并渲染，拼成一条最终成片 mp4。
3. **保留原音**：成片保留各片段原始音轨（转场处 acrossfade）；配音/配乐在后续阶段叠加。

成片落盘后可「送去配乐」交接给后续阶段。

### 核心决策

| 维度 | 决策 |
|------|------|
| 落地路线 | **方案 C 渐进式**：v1 看片+剔除+排序+trim+一键拼接（默认/手动转场，零新依赖）；**v2** 加全套 CV 自动推荐 |
| 最终能力 | 全套 CV（PySceneDetect + OpenCV 颜色直方图/SIFT + Farneback 光流多维评分） |
| 渲染引擎 | **ffmpeg 内置 `xfade`（视频）+ `acrossfade`（音频）**，subprocess 调用；排除 gl-transition |
| CV 运行位置 | 主进程 `FunctionWorker(QThread)`（一次性批处理，OpenCV C 层释放 GIL；子进程 agent 为过度工程，仅 v3 视需要再下沉） |
| 接入位置 | 「视频后期」容器页**新增首个 tab「成片」** → `[成片, 配音, 配乐]`；门禁 `production` |
| 片段来源 | 自动列出 `video_output_dir` 项目生成片段 **+** 手动添加外部 mp4 |
| ffmpeg | **随包分发 `ffmpeg.exe`/`ffprobe.exe`**，绝对路径调用（顺带治理 `pcm_cache` 同样的裸 PATH 脆弱性） |
| 成片音轨 | **保留片段原音**，转场处 acrossfade |
| 转场效果库 | v1 精选 ~8 个老版本兼容效果（见 §6.2） |
| 配乐交接 | **手动**「送去配乐」按钮预填新建 soundtrack 任务的 mp4 字段（不自动） |

### 不在本期范围

- 段**内部**的重剪（只在段头尾 trim，不切段中间）。
- gl-transition / GLSL 自定义转场、GPU 转场（v1/v2 都用 xfade 内置效果）。
- 卡点/节拍同步（无音乐阶段；卡点属后续配乐阶段）。
- 转场建议的外部 JSON Schema 导入（豆包文档的「转场设计建议」高级场景）——本期用 UI 内逐切口手动覆盖替代。
- 全量 44 个 xfade 效果开放（v1 用精选集）。

---

## 2. 接入位置与模块边界

### 2.1 导航接入（`nav_config.py`）

「视频后期」(`video_post`) 已是 `QTabWidget` 容器页（`VideoPostPage`），现 tab 为 `[配音, 配乐]`。新增「成片」为**首个 tab**：

```python
VIDEOPOST_TABS = [
    ("compose", "成片"),     # 新增，置首
    ("dubbing", "配音"),
    ("soundtrack", "配乐"),
]
FUNCS += [("成片", "compose")]      # 供容器页装配 + LABELS/PHASE 兼容
PHASES[3] = ("③ 视频出片", ["video_gen", "compose", "dubbing", "soundtrack"])
TASK_KEYS.add("compose")
ICONS["compose"] = "video.svg"      # v1 复用现有图标（或新增 compose.svg）
```

`app_shell._build_pages` 中 `builders["compose"] = self._make_compose_page`，构造后塞入 `_func_pages["compose"]`，由 `VideoPostPage.set_tabs` 装配。**复用 `TaskWorkspacePage`**（注入 `editor_factory/wire_editor/payload_of/on_persist/title_for`），不造新页壳。门禁顺序改动需同步 `tests/test_ui/test_nav_config.py`。

### 2.2 新增模块（每个职责单一、可独立测试）

| 模块 | 职责 | Qt 依赖 |
|------|------|---------|
| `core/composition_model.py` | `CompositionModel` / `ReelClip` 数据模型（to_dict/from_dict/validate/reorder/update） | 无（纯逻辑，纯函数单测） |
| `core/ffmpeg_locate.py` | 解析随包 `ffmpeg`/`ffprobe` 绝对路径，`shutil.which` 兜底，缺失抛明确错误 | 无 |
| `core/transition_render.py` | 由 `CompositionModel` 构建 ffmpeg `filter_complex`（归一化+trim+xfade+acrossfade+offset 累计）并执行；失败降级分段+concat | 无 |
| `core/transition_analyzer.py` | **（v2）** CV 评分：取边界帧 → 直方图/SIFT/光流 → 0–1 评分 → 转场映射 | 无（用 cv2/scenedetect） |
| `ui/panels/compose_panel.py` | 成片编辑器（走马灯+预览+trim+inspector+渲染） | 是 |
| `ui/widgets/compose/clip_strip.py` | 片段走马灯（缩略图卡、拖拽排序、保留切换、切口圆点） | 是 |
| `ui/widgets/compose/trim_bar.py` | 缩略图刷条 + 双手柄设入/出点 | 是 |
| `ui/widgets/compose/transition_inspector.py` | 切口转场编辑（效果/时长/来源/锁定） | 是 |

复用既有：`ui/widgets/video_preview_widget.py`（预览播放）、`ui/worker.py`（`FunctionWorker`/`BatchWorker`）、`ui/pages/task_workspace_page.py`、`ui/panels/video_task_manager_panel.py` 风格的成片任务列表。

---

## 3. 数据模型（`core/composition_model.py`）

照搬 `core/video_timeline_model.py` 的 dataclass + 序列化风格。

```python
@dataclass
class ReelClip:
    clip_id: str                      # _gen_id() 生成
    path: str                         # mp4 绝对路径
    keep: bool = True                 # 看片剔除
    in_point: float | None = None     # 头 trim（秒），None=从头
    out_point: float | None = None    # 尾 trim（秒），None=到尾
    duration: float = 0.0             # ffprobe 实测原时长（只读缓存）
    # 到「下一个保留片段」的转场（最后一个保留片段该字段忽略）
    auto_transition: str | None = None       # CV 推荐效果名（v2 填）
    auto_duration: float | None = None
    user_transition: str | None = None       # 手动覆盖
    user_duration: float | None = None
    locked: bool = False                      # 重跑 CV 不覆盖
    cv_scores: dict = field(default_factory=dict)  # {hist,feature,motion,score}（v2 只读缓存）

    # effective_transition = user_transition ?? auto_transition ?? 默认('dissolve')
    # effective_duration   = user_duration  ?? auto_duration  ?? 0.5
    # trim 后时长 = (out_point or duration) - (in_point or 0)

@dataclass
class CompositionModel:
    clips: list[ReelClip]
    fps: int = 30
    width: int = 1920
    height: int = 1080
    pix_fmt: str = "yuv420p"
    output_prefix: str = "compose"
    # to_dict / from_dict / validate / _gen_id / reorder_clips(ordered_ids) / update_clip(id, **f)
    # kept_clips() -> [保留片段，按当前顺序]
    # validate() -> (ok, msg): 至少 1 个保留片段；每个非末尾保留片段 trim 后时长 >= effective_duration
    #               （否则该切口降级硬切并告警，不阻断）
```

**持久化**：照搬 `config.py` 的 `video_tasks`/`soundtrack_tasks` 三处改动，新增 `compose_tasks: list`（`field(default_factory=list)` + to_dict 区块 + load 反序列化）。成片任务存储结构与 `VideoTask` 平行（`ComposeTask{id, name, status, output_mp4, updated_at, composition: dict}`），新建 `core/compose_task_store.py`（照搬 `video_task_store.py`）。

---

## 4. 渲染管线（`core/transition_render.py`，v1 即完整）

输入：`CompositionModel`（已剔除/排序/trim/转场参数齐备）。输出：单条成片 mp4 路径。

1. **探测**：对每个保留片段 `ffprobe` 取时长/分辨率/帧率/SAR/pix_fmt/有无音轨/是否 VFR。
2. **归一化**（xfade/acrossfade 硬要求一致）：每段
   `scale=W:H:force_original_aspect_ratio=decrease, pad=W:H:(ow-iw)/2:(oh-ih)/2, fps=FPS, format=PIX, setsar=1, settb=AVTB`；
   音频 `aresample=48000, aformat=channel_layouts=stereo`。无音轨的片段补静音 `anullsrc` 以保证 acrossfade 链统一。
3. **trim**：用 `-ss in_point -to out_point`（或 filter `trim/atrim`）。trim 后时长记作 `d_i`。
4. **拼接（单条 `filter_complex`）**：
   - 视频链逐切口 `xfade=transition=<效果>:duration=<t_i>:offset=<off_i>`；
   - 音频链逐切口 `acrossfade=d=<t_i>`（与视频同 duration）；
   - **offset 累计**（头号 bug 源，必须用实测 `d_i`）：`off_i = Σ_{k<=i} d_k − Σ_{k<=i} t_k`（即前 i+1 段总时长减去已应用转场总时长）。
5. **降级**：单趟 filter_complex 失败 → 分段两两渲染 + `concat`（接缝硬切，记日志告警画质/接缝代价）。
6. **校验**：`validate()` 中 trim 后段时长 < 该切口转场时长 → 该切口自动降级硬切（transition=fade 0 或直接 concat 该段）并告警，不阻断整体。
7. **ffmpeg 定位**：经 `core/ffmpeg_locate.py` 拿随包 `ffmpeg.exe` 绝对路径；缺失 → UI 明确报错（不静默失败）。

渲染在 `FunctionWorker`/`BatchWorker(QThread)` 执行：`item_done` 逐切口/逐阶段上报进度，`finished_with_result` 回传成片路径，`failed` 报错。成片落 `video_output_dir/compose_<task_id>.mp4`，写回 `ComposeTask.output_mp4`。

---

## 5. CV 智能转场分析（`core/transition_analyzer.py`，v2）

`FunctionWorker(QThread)` 内对**每个保留切口**（相邻两保留片段）：

1. **取边界帧**：前段「末尾稳定帧组」+ 后段「开头稳定帧组」。段内转场已完成 → **留 0.2–0.3s 余量**避开段内淡入淡出过渡帧；每侧取 3–5 帧**取中位**抗噪。PySceneDetect 可选用于定位段内末/首镜头边界（多数可退化为按时间取头尾帧）。
2. **多维特征**：
   - 颜色：`cv2.compareHist`（HSV 直方图相关性）→ `hist`∈[0,1]；
   - 结构：SIFT（`opencv-python` 主包，4.4+ 专利过期）+ BFMatcher + Lowe ratio → 匹配率 `feature`∈[0,1]；
   - 运动：`calcOpticalFlowFarneback`（跨片段两帧是伪运动场，**弱用**，权重 0.2，取不到特征给中性 0.5）→ 方向倾向 + `motion_discontinuity`。
3. **综合评分**：`score = 0.4·hist + 0.4·feature + 0.2·(1 − motion_discontinuity)`（权重可配）。
4. **映射** → `auto_transition`/`auto_duration`（写入未 `locked` 的切口）：

| score | 运动 | 效果类别 | 默认效果 / 时长 |
|-------|------|----------|----------------|
| 高（≥ 高阈值） | 无/弱 | 万能适配 | `dissolve` / `fade` · 0.5s |
| 中 | 有明确方向 | 方向推进 | `smoothleft/right/up/down`（按光流方向）· 0.6s |
| 低（< 低阈值） | 大变化 | 创意 | `circleopen` / `pixelize` · 0.7–0.8s |
| trim 后过短 | — | — | 硬切 |

`locked` 切口不被重跑覆盖；`effective = user ?? auto ?? 默认`。**v2 才改 `build/drama_shot_master.spec`** 移除 `cv2` exclude（见 §8）。

---

## 6. UI 设计

布局已用户拍板，详见 `docs/explorer/成片合成-layout.html`。要点：

### 6.1 结构（成片 tab 内，master-detail）
- **左**：成片任务列表（`+ 新建成片任务`）。
- **右编辑器**（`compose_panel`）：
  - 顶部工具栏：任务名 + `⟳ 列出生成目录` `＋ 添加片段` | `✦ 一键智能转场`(主按钮)。
  - **片段走马灯**（`clip_strip`）：缩略图卡（封面=cv2/ffmpeg 抽帧，角标「N 镜」，左上勾选保留/剔除，右上拖拽柄）；剔除卡变灰标「已剔除」；**卡片间圆点=转场切口**（点击编辑；硬切显示方块；AI 推荐带紫色角标）。
  - **下方左**：`video_preview_widget` 预览（选中片段 / 整片切换）+ **trim 条**（`trim_bar`：缩略图刷条 + 双蓝手柄设入/出点；提示「仅存入/出点，渲染时实裁」）。
  - **下方右 inspector**：选中切口 → 转场编辑（效果下拉 / 时长 0.3–2.0s 滑条 / 来源 AI自动·手动覆盖 / ☐锁定 / ↺重置为AI / 应用到全部）。
  - 底部：渲染进度条 + 「归一化 1080p/30fps · 保留原音」状态 + `送去配乐 ›`。

### 6.2 v1 转场效果精选集（xfade 名）
`fade` / `dissolve` / `smoothleft` / `smoothright` / `smoothup` / `smoothdown` / `circleopen` / `pixelize` + **硬切**(none)。运行时用 `ffmpeg -h filter=xfade` 校验可用性，不可用项灰掉。

### 6.3 缩略图抽帧
v1 用随包 `ffmpeg -ss <t> -frames:v 1`（避免引入 cv2）；后台 QThread + 限尺寸(160px) + 按 path 缓存。v2 起可改 cv2 抽帧或维持 ffmpeg。

---

## 7. 分阶段交付

- **v1（零新依赖、零打包风险，spec 不动）**：成片 tab + 任务列表 + 自动列目录/手动添加 + 看片剔除/拖拽排序/头尾 trim + 逐切口默认/手动选转场 + 一键 xfade+acrossfade 拼接（保留原音）+ 进度/预览/`送去配乐` + 随包 ffmpeg + `ffmpeg_locate` 探活。数据模型/UI 契约**一次设计到位**（含 `auto/user/locked/cv_scores` 字段），v1 `cv_scores` 留空。
- **v2**：`transition_analyzer` 全套 CV 自动推荐（§5）；改 spec 引入 `cv2`/`scenedetect`（§8）。UI 契约不变（`一键智能转场`按钮从「规则/默认」切到「真 CV」）。
- **v3（可选）**：若 v2 实测 OpenCV 拖垮主进程或渲染过长，按调研方案 B 将 CV+渲染下沉为一次性子进程 `compose_agent`（复用 `main.py --run-agent` 分发），UI 契约不变、迁移低成本。

---

## 8. 打包与依赖（风险治理）

- **v1**：仅新增**随包 `ffmpeg.exe`/`ffprobe.exe`**（标准版，无需 GL 定制）。`build/drama_shot_master.spec` 把二进制加入 `datas/binaries`，`ffmpeg_locate` 用 `sys._MEIPASS`/安装目录绝对路径。无 Python 重依赖。
- **v2 引入 cv2 的必做改动**（调研明确）：
  - 移除 `build/drama_shot_master.spec` excludes 中的 `'cv2'`；
  - PyInstaller：`--hidden-import cv2` + 保持 **onedir** + **关 UPX**（否则 `Recursion is detected during loading of cv2`）；`scenedetect` 需 `--hidden-import platformdirs.windows`；
  - 项目混用 Nuitka（`screenwriter_lifecycle._is_frozen` 同探 `__compiled__`/`sys.frozen`）：Nuitka 侧 `--include-package=cv2`；
  - 体积 +35–45MB（opencv 解包 + 多个大 .dll），冷启动变慢——这是把它推迟到 v2 的根本原因。
- 依赖固定：`opencv-python>=4.5`（非 contrib）、`scenedetect>=0.6.4,<0.7`、`numpy`(已有)、`PySide6 QtMultimedia`(已随 wheel)。

---

## 9. 测试

- **纯逻辑单测**（无 Qt）：
  - `composition_model`：to_dict/from_dict 往返、reorder、update、`kept_clips`、`validate`（空保留 / trim<转场降级）、`effective_*` 覆盖优先级。
  - `transition_render`：给定时长序列 → 断言 `offset` 累计公式、filter_complex 字符串结构（含 xfade/acrossfade/归一化）、降级路径。
  - `ffmpeg_locate`：随包路径优先、PATH 兜底、缺失抛错。
  - **（v2）** `transition_analyzer`：评分→映射表（喂合成帧/桩特征，断言分档与方向）。
- **Qt 测试**（offscreen）：`compose_panel` 实例化、走马灯保留/排序/剔除信号、inspector 覆盖/锁定回写模型、`送去配乐` 信号。
- **nav 回归**：`test_nav_config.py` 同步 `VIDEOPOST_TABS`/`PHASES`/`TASK_KEYS`。
- **集成冒烟**：用 2–3 个真实短 mp4 跑一趟渲染，校验成片时长 ≈ Σd − Σt 且音画同步。

---

## 10. 边界与风险

| 场景 | 处理 |
|------|------|
| RunningHub 片段参数不一致 / VFR | 渲染前强制归一化（scale+fps+format+setsar+settb+aresample），VFR → CFR |
| trim 后片段时长 < 转场时长 | `validate()` 告警 + 该切口降级硬切 |
| 单趟 filter_complex 失败 | 降级分段渲染 + concat（接缝硬切，记日志） |
| ffmpeg 缺失 | `ffmpeg_locate` 抛错，UI 明确提示（不静默失败）；顺带治理 `pcm_cache` |
| 片段无音轨 | 补 `anullsrc` 静音保证 acrossfade 链统一 |
| CV 取不到特征（v2） | 该项给中性 0.5，光流权重低；整体兜底走「万能适配」效果 |
| 段内过渡帧污染评分（v2） | 留 0.2–0.3s 余量 + 多帧取中位 + 可选 PySceneDetect 定位镜头边界 |
| cv2 打包（v2） | 见 §8（spec/UPX/Nuitka），体积 +35–45MB |

---

## 11. 验收

- v1：能从生成目录列出片段并手动补充；可剔除/排序/trim；一键拼接出**保留原音**的成片 mp4（默认/手动转场）；进度可见；`送去配乐` 预填成功；终端机无需预装 ffmpeg。
- v2：`一键智能转场`对每个未锁切口给出 CV 推荐（效果+时长），可手动覆盖与锁定，重跑不覆盖锁定项。
