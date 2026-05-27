# 曲库匹配 / 多路候选 设计

**目标:** 在 AI 生成配乐之外,增加"本地曲库匹配"作为另一路候选来源;用户可逐任务选择候选来源(AI / 曲库 / 都要)与音乐类型(纯音乐 / 带词 / 都要),让每段配乐有**多路候选**可试听选优。

**背景:** 见 `E:\Rui\笔记\AIEngineer\AIEngineer\漫剧\01-Workflow配置\06-视频配乐\配乐库方案调研.html`——主张免费商用、非AI、纯音乐(人类创作),优先国内合规平台(光厂/曲多多),流程为人工 搜索→筛选→试听→下载→存授权。工程现实:这些平台基本无开放 API,故工具做**本地曲库**(用户按调研手动下载好授权曲目入库)的索引与匹配,而非在线全网搜索。

**架构:** 新增 `sound_track_agent/music_library.py`(本地索引 + Track)与 `sound_track_agent/library_matcher.py`(标签匹配,接口化,未来可接 CLAP / 在线 provider)。候选模型加 `source`,生成阶段按任务的来源/类型设置同时产 AI 与曲库候选(曲库候选裁成段时长片段),两路都进 `seg.candidates`,沿用既有 ②试听选优 / mix。自包含:引擎在 `sound_track_agent`、UI 在 `drama_shot_master`,无 sibling import,cfg 鸭子类型读。

**技术栈:** soundfile(时长)、librosa(BPM,已有)、ffmpeg(片段裁切)、PySide6(库管理对话框 + 控件)。不引入新重依赖(CLAP 为后续可插拔)。

---

## 1. 范围与分期

一个 spec,分三期实施(实现计划按阶段排任务):
- **一期·曲库引擎(无UI):** `music_library`(索引/Track/build/save/load)+ `library_matcher`(TagMatcher,接口化)。
- **二期·多路候选:** `BGMCandidate.source/title/license`;生成阶段按 `bgm_sources`/`music_type` 产 AI + 曲库候选(含片段裁切);单段重生成同理。
- **三期·UI:** ①来源/类型控件、②候选来源标识、曲库管理对话框、设置项。

每期独立可测、可交付。

## 2. 决策(已与用户确认)

| 决策点 | 选定 |
|--------|------|
| 曲库来源 | 本地为主;provider 接口化,在线(Pixabay 等)后续可插拔 |
| 匹配信号 | 标签匹配为主;matcher 接口化,CLAP 后续可接 |
| 打标方式 | 导入自动初判(时长/BPM/文件夹猜标签)+ 库管理对话框人工校正,索引 library.json |
| 来源控制 | 每任务可选来源 + 音乐类型 |
| 默认来源 | 新任务默认 `["ai", "library"]` |
| 默认音乐类型 | `"instrumental"`(纯音乐,最安全) |
| 片段选取 | v1 从起点裁(段时长+crossfade 尾);最佳片段选取留后续 |

## 3. 数据模型

**`Track`**(`sound_track_agent/music_library.py`,dataclass):
```
path: str            # 音频文件绝对路径
title: str           # 默认取文件名 stem
duration: float      # 秒,soundfile 读
bpm: float           # librosa 估,失败为 0.0
mood_tags: list[str] # 情绪/场景标签
genre: str           # 风格流派
has_vocals: bool     # 带词=True / 纯音乐=False
license: str         # 授权说明(自由文本,如 "CC0"/"光厂免费商用")
source: str          # 来源平台,如 "光厂"/"Pixabay"/""
```
含 `to_dict`/`from_dict`(缺字段给默认)。

**索引文件:** `<music_library_dir>/library.json` = `{"tracks": [Track.to_dict(), ...]}`。

**`BGMCandidate`** 扩展(`session.py`)新增:
```
source: str = "ai"   # "ai" | "library"
title: str = ""      # 曲库候选的曲名(AI 候选留空)
license: str = ""    # 曲库候选的授权(AI 候选留空)
```
`to_dict`/`from_dict` 序列化;旧数据 `from_dict` 默认 `source="ai", title="", license=""`(向后兼容)。

**任务级**(存 task dict + 镜像到 session 以便续跑):
```
bgm_sources: list[str] = ["ai", "library"]   # 候选来源
music_type: str = "instrumental"             # "instrumental" | "vocal" | "both"
```

**全局 cfg**(`drama_shot_master/config.py`)新增:
```
music_library_dir: str = ""        # 曲库目录(空=未配置,曲库来源不可用)
library_matcher: str = "tag"       # 匹配器类型,未来 "clap"
library_candidates: int = 2        # 每段曲库候选数 top-N
```
持久化进 update_settings + load_config。

## 4. 曲库索引与管理

**`music_library.py`**:
- `build_index(library_dir, *, existing=None) -> list[Track]`:递归扫 `library_dir` 下音频(.mp3/.wav/.flac/.m4a)。每文件自动初判:
  - `duration`:soundfile.info。
  - `bpm`:librosa.beat.beat_track(失败 → 0.0,降级不中断)。
  - `genre`/`mood_tags`:从相对路径的文件夹名 + 文件名分词猜(命中内置词表,如 古风/悬疑/甜宠/动作/紧张/温暖…);猜不到留空/[]。
  - `has_vocals`:若路径含 "带词/vocal/人声" → True,含 "纯音乐/inst/instrumental/bgm" → False,否则默认 False。
  - `title`:文件名 stem;`source`/`license`:空(待人工补)。
  - 与 `existing`(已存 library.json)按 `path` 合并:**已存在的曲目保留其人工字段**(mood_tags/genre/has_vocals/license/source/title),仅刷新 duration/bpm;新文件入库;已删文件移除。
- `load_index(library_dir) -> list[Track]`(无文件返回 [])、`save_index(library_dir, tracks)`。

**库管理对话框**(`drama_shot_master/ui/dialogs/music_library_dialog.py`):
- 顶部:曲库目录(LineEdit + 浏览)、「扫描导入」按钮(调 build_index 合并)。
- 中部:QTableWidget,每行一曲,列:标题 / 情绪标签(逗号分隔可编辑)/ 风格 / 带词(复选)/ BPM / 授权 / 来源。BPM 只读,其余可编辑。
- 底部:保存(写 library.json)。
- 长任务(扫描 + BPM 估算)用 FunctionWorker 后台跑,避免卡 UI。

## 5. 匹配器

**`library_matcher.py`**:
- 协议(鸭子类型):`match(segment, tracks, *, music_type, top_n) -> list[Track]`。
- **`TagMatcher`**(一期):
  - 目标标签:复用 `prompt_composer` 把 `segment.emotion`(labels/valence/arousal)+ `global_style` 映射成一组期望标签/关键词(纯逻辑,不调外部)。
  - 过滤:`music_type="instrumental"` → 仅 `has_vocals=False`;`"vocal"` → 仅 True;`"both"` → 不滤。过滤后为空则返回 []。
  - 打分:`0.6*标签重合(加权 Jaccard, mood_tags+genre vs 目标标签) + 0.25*时长适配(track.duration ≥ seg.duration 加分,过短轻罚) + 0.15*BPM 拟合(与 compose 的目标 bpm 距离,track.bpm=0 则中性)`。
  - 返回按分降序 top_n。纯函数,零 I/O,可单测。
- 工厂 `get_matcher(cfg)`:读 `cfg.library_matcher`,"tag"→TagMatcher;未知 → TagMatcher 兜底。未来 "clap"→ClapMatcher(同协议)。

## 6. 多路候选生成

**片段裁切**(`music_library.py` 或 `mixdown` 复用):`make_excerpt(track_path, out_path, seconds) -> str`:ffmpeg `-t (seconds + crossfade尾)` 从起点裁;曲目短于目标则输出整首(ffmpeg `-t` 超长=整首)。

**候选组装**(`facade.py`):新增 `generate_candidates(seg, sess, *, cfg, work_dir, workflow_id, seeds_count) -> list[BGMCandidate]`:
- `srcs = getattr(sess, "bgm_sources", ["ai", "library"])`;`mtype = getattr(sess, "music_type", "instrumental")`。
- `cands = []`
- 若 `"ai" in srcs`:现有 ACE-Step 路径生成 → 标 `source="ai"`,append。
- 若 `"library" in srcs` 且曲库可用(cfg.music_library_dir 有效且 library.json 非空):
  - `tracks = load_index(dir)`;`hits = get_matcher(cfg).match(seg, tracks, music_type=mtype, top_n=cfg.library_candidates)`;
  - 每 hit → `make_excerpt(hit.path, work_dir/segN/lib_{i}.wav, seg.duration)` → `BGMCandidate(path=excerpt, seed=-1, prompt=tags, source="library", title=hit.title, license=hit.license)`,append。
- 返回 cands。
- 接线:`stages_factory.build_stages` 的 `generate` 闭包改调此组装(注入 cfg/matcher/索引);`facade.regenerate_segment` 同样调它(换候选、清选定)。两者共用,DRY。

**门控边界:** 曲库来源被选但 cfg.music_library_dir 未配置/索引空 → 跳过曲库候选(不报错,仅 AI);若 AI 也没选且曲库不可用 → 该段 candidates 为空(UI 提示去配置曲库或开 AI)。

下游 ②试听选优 / ③卡点 / mix(clip_durations/gains/pump)**无需改**:曲库候选与 AI 候选都是 ≈段时长的 wav。

## 7. UI

- **①配置页**(`soundtrack_task_window.py`):加「配乐来源」(三态:AI/曲库/都要,用两个复选或一个 combo)写 `task.bgm_sources`;「音乐类型」combo(纯音乐/带词/都要)写 `task.music_type`。
- **②试听选优**(`segment_review_widget.py`):候选按钮文案带来源标识——AI:`▶ 候选N·AI`;曲库:`▶ 候选N·曲库《{title}》`,tooltip 显示 `license`。
- **曲库管理对话框**:见 §4;入口放 设置→配乐 对话框里加「管理曲库…」按钮,或菜单「设置→曲库…」。
- **设置→配乐**(`soundtrack_settings_dialog.py`):加 曲库目录、每段曲库候选数、(matcher 类型可暂隐藏/留默认 tag)。

## 8. 测试

- **`music_library`**:对临时目录(生成几个 tone wav,按 `古风/纯音乐/x.wav`、`甜宠/带词/y.wav` 文件夹约定)→ build_index 断言 duration>0、has_vocals 推断、genre/mood 猜中、bpm≥0;合并保留人工字段(改一条 mood_tags 后重扫仍在);save/load 往返。
- **`library_matcher`**:构造 Track 列表 + 带 emotion 的 segment,断言:标签重合高者排前、music_type 过滤(纯音乐排除 has_vocals)、top_n 截断、过滤后空返回 []。纯函数。
- **`make_excerpt`**:tone wav 裁到 0.5s,sf.info.duration ≈ 0.5(+尾)。
- **多路候选(facade)**:注入假 matcher(返回固定 Track)+ 假 AI generate,断言:`bgm_sources=["ai","library"]` → candidates 同时含 source="ai" 与 "library";`["library"]` 且 music_type=instrumental → 只含曲库且无带词;曲库未配置 → 回退仅 AI。
- **UI smoke(offscreen)**:①来源/类型控件写 task;②候选按钮带来源标识;库管理对话框扫描(monkeypatch build_index)+ 编辑 + 保存写 library.json。避免模态阻塞。
- **自包含**:引擎全在 `sound_track_agent`,UI 在 `drama_shot_master`,无 sibling import、无新重依赖。

## 9. 错误处理

- 索引/BPM/裁切失败 → 降级(bpm=0、用整首、跳过该曲),不中断生成管线。
- 曲库目录不存在/library.json 损坏 → load_index 返回 []、曲库候选数为 0,记录提示。
- 带词候选与对白冲突属用户选择:默认 `instrumental`;UI 在「音乐类型」旁注明"带词适合无对白段(片头/尾/蒙太奇)"。

## 10. 已知局限 / 后续

- v1 片段从起点裁,非"最精彩段";后续可加能量/副歌检测选段。
- v1 matcher 为标签法;CLAP(音频-文本嵌入)与在线 provider(Pixabay API)为接口化后续。
- has_vocals 自动判断依赖文件夹/文件名约定;精确判断(Demucs 人声能量)留后续。

## 11. 文件清单

新增:`sound_track_agent/music_library.py`、`sound_track_agent/library_matcher.py`、`drama_shot_master/ui/dialogs/music_library_dialog.py`。
改:`sound_track_agent/session.py`(BGMCandidate 字段)、`sound_track_agent/stages_factory.py` + `facade.py`(generate_candidates 接线)、`drama_shot_master/config.py`(3 个全局字段)、`soundtrack_task_window.py`(来源/类型控件)、`segment_review_widget.py`(来源标识)、`soundtrack_settings_dialog.py`(曲库目录/候选数 + 管理入口)。
对应测试若干。
