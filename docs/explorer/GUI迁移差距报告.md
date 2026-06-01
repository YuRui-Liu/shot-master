# GUI 迁移差距报告（原 PySide6 → Web）

> 2026-06-01 五路并行审计综合。对比原 PySide6 全部功能 vs 当前 web/ 页面，列出还需迁移/接活的功能。
> 关联 [[gui-web-rewrite-strategy]]。结论先行：**后端 SSE/REST 多已就绪，差距集中在 ① 编剧向导链编排 ② 导演台自由时间轴 ③ 拆拼裁接线 ④ 资源库/概览/设置/任务中心的后端缺口 ⑤ DAW 真功能**。

## 总览
- ✅ **已真接通**：编剧 SSE 8 路由全可用 + ideate 出候选(验证过)；出图 /imggen；转场 /transition analyze+render；TTS /tts(design)；assets genres/styles 实拉；项目 /projects list/open/create。
- ⚠️ **接了但语义/链路不完整**：见下分区。
- ❌ **整块缺失**：编剧向导链编排、剧本/分镜/出图prompt 阶段页、导演台自由时间轴、拆/拼/裁接线、资源库 ref_index、概览数据、设置落盘、任务中心。

---

## A. 剧本创作链（最高优先 — 用户已发现）
后端 8 路由齐全，**差距纯在前端未串成向导链**。
| 优先级 | 缺口 | 现状 |
|---|---|---|
| 高 | **立意多轮续聊**(messages 累积深挖/调整) | ideate.html 每次硬编码单条 message，无续聊输入框/历史 |
| 高 | **立意持久化/回显**(切页不丢、读创意.json 回显 messages/candidates/selected) | 进页不读盘，candidates 仅内存，刷新即丢 |
| 高 | **选定候选→推进剧本** | postMessage `ideate.advance` 发了，但 app.html **未监听该消息**→断链 |
| 高 | **剧本页可达 + 真保存** | script.html 无导航入口(孤儿)；保存是假(只改按钮文字不落盘) |
| 高 | **分镜阶段页**(storyboard：角色行/镜头表/warnings/JSON校验保存) | Web 无编剧分镜脚本页(storyboard-board 是出图视角) |
| 中 | **出图prompt 阶段页**(prompts：宫格分组/产物树/单组全量生成) | Web 完全无 |
| 中 | 视频prompt/配音prompt 阶段页项目级持久化(模板/语言存 _config.json) | 被改造成独立"视频/配音"页，丢阶段语义 |
| 高 | **阶段门禁 + 上游 banner**(revalidate_upstream/pipeline_lock) | 各页独立，无上游自检、无 stepper 可点跳转 |
| 中 | 题材/风格真实选择落盘 project.json(下游 assemble_gen_context 注入) | ideate 选模板是占位循环，不落盘，下游 script 只占位"继承" |
| 低 | 多项目后台并发 worker / 一键重试 / 空响应诊断 | Web 单 AbortController，无 |

**根因**：app.html 把"剧本创作"只指向 ideate.html；script/storyboard/prompts/video/audio 被拆成平级独立页，丢了"创意→剧本→分镜→出图prompt→视频prompt→配音prompt"的向导链 + 上游门禁 + 统一项目编排。

## B. 视频生成 · 导演台（用户已发现 — 参考 视频生成-自由模式.png）
原导演台=**单提交多段时间轴**(一条轴拼多段成一个视频)；Web 模式1=逐卡独立出 clip（架构错配）。
| 优先级 | 缺口 |
|---|---|
| 高 | **自由多段时间轴**(帧缩略片段条/可拖拽/重排/单次提交拼一条) — Web 无,是独立卡 |
| 高 | **图片池 + 批量导入**(拖拽 OS 文件) — Web 无 |
| 高 | **真实首帧/参考图路径 + 上传** — Web 首尾帧只是布尔占位,永远空 |
| 高 | **音频轨 Add Audio + use_custom_audio** — Web 无 |
| 高 | **global_prompt 全局参数 + 启用开关** — Web 把它误当本卡基底 |
| 高 | **分辨率预设 + 自定义 WxH** — Web 只有 ?aspect= |
| 高 | **per-segment Guide(0-1)** — Web 无 |
| 中 | 时长帧/秒可切(Web 只 1-8s 整数滑块)、fps 可调(写死24)、noise_seed、epsilon、输出名前缀、Add Text 段、批量真生成、提交校验、✨优化提示词、总时长状态栏、任务持久化 |
| 中 | **/video/ltx body 太窄**(7字段) vs LTXDirectorSpec(13+字段：global_prompt/use_global/segments/audio_segments/use_custom_audio/frame_rate/resolution/custom_wh/noise_seed/epsilon/filename_prefix)→后端契约要扩 |
| 中 | **画质 key 不一致**：Web `hd_director` vs 注册表 `director_v3`(workflow_profiles.py) — 后端需映射(否则 hd 取不到 profile) |

注：导演台工作流注册在 `core/workflow_profiles.py`(director/director_v3)，非 tts_profiles。

## C. 出图 / 拆拼裁 / 资源库
| 优先级 | 缺口 |
|---|---|
| 高 | **拆/拼/裁 全未接后端**(imaging.py 的 /split /trim /combine /batch_split /detect_borders /infer_grid /cell_boxes /crop_aspect **全已实现**，但 web 自由模式 execBtn/检测按钮全是假进度+alert 占位) — **最易补** |
| 高 | 出图**参考图区 + @标签 + 文生/图生模式判定** — Web references 写死空 |
| 高 | 出图/拆图**任务管理**(任务表/新建/复制/删/状态/持久化) — Web 无 |
| 高 | 资源库 **ref_index 读/写后端缺**(角色/场景/道具 ref 生成/锁定/一致性) — assets.py 只有 genres/styles，无 ref 端点；Web 全占位数据 |
| 高 | 资源库 ref 生成/从剧本提取实体/单条重生 — 无后端 |
| 中 | 拆图**重采样/AI 超分**(后端 /split 本身也不含,需补)、快捷提示词库、画质档(2K/1K)、画幅6档、每条张数 |
| 中 | 批处理输出目录选择/打开源图加载缩略图/预览叠加 — 全占位 |
| 中 | 单图 HD 超分(Web 多出 HD 开关但 provider 无 upscale,未兑现) |

## D. 配音 / 配乐 / 视频后期(DAW/转场)
| 优先级 | 缺口 |
|---|---|
| 高 | 配音**声音克隆模式**(4 情感子模式/参考音频/情感向量) — **后端 tts.py 已支持 clone，前端未接** |
| 高 | 配乐**整管线 advance + 出片 mixdown**(切镜→段落→情绪→生成→对齐→混音) — 后端 /soundtrack 只有 compose_prompt/generate_bgm/batch,缺 advance/mixdown |
| 高 | **真实多轨混音**(numpy 下混/硬限幅) — Web wavesurfer 各轨独立,无真下混 |
| 高 | **卡点检测(光流)+卡点混音/泵感** — 后端无 accent 端点,Web ACCENTS 写死 |
| 高 | DAW **真实波形接 media_agent 输出** — Web 用 CDN demo 音频 |
| 高 | **播放头 WS** ws://…/soundtrack/ws — 后端不存在,Web 本地定时器演示 |
| 中 | SFX 检测/生成、框选生成叠加子轨(3d overlay)、情绪曲线/AI指令、段落拖拽/undo、导出成片、配音入轨 — 后端均无端点 |
| 中 | 转场：添加片段/列生成目录/缩略图抽帧/trim 实裁/拖拽排序/送配乐传参 — Web stub(clips 硬编码) |
| 低 | 转场 ffmpeg_args 干跑(后端有,Web 未用)、真实渲染进度(同步无流,伪进度) |

## E. 首页 / 概览 / 设置 / 任务中心 / 壳
| 优先级 | 缺口 |
|---|---|
| 高 | **新建项目**缺 选目录→分配P-NNN→**写 manifest**→题材/风格向导(后端 /projects/create 只建空目录登记) |
| 高 | **打开目录**：welcome 发 `project.openDirRequest`,**app.html 壳未监听**(只听 project.open);浏览器降级拿不到绝对路径 |
| 高 | **概览页全静态**：无 fetch、无跳转、无编辑圣经/题材；**后端无 /project/overview 聚合端点** |
| 高 | **设置全 section 占位**：保存不落盘、无校验、无测试连接；**后端无 /config GET/PUT** |
| 高 | **任务中心整体缺失**：标题栏按钮无 onclick/无抽屉/无聚合;**后端无任务聚合端点** |
| 高 | 项目管理 移除显示/删文件夹 仅改内存数组;**后端无 /recent/remove|delete_folder|clear** |
| 中 | open 项目不调 /projects/open 置顶、不校验 path 存在;最近项目只走 recent_mgr 不读 compass registry(丢 project_id) |
| 中 | 流程锁门禁(侧栏置灰)、项目载入统一编排(_load_project_into_ui)、授权巡检 |
| 低 | 面包屑阶段前缀、下一步提示挂侧栏、帮助/关于、coverflow 加号卡、边缘缩放、概览阶段口径(7 vs 5 vs 侧栏6 不一致需统一) |

> 注：双 agent lifecycle **web_app.py 已 spawn**(media+screenwriter)，审计 E 说"无人 spawn"是因其只看 app_shell——实际 web_app.py 已处理；但 app.html 在浏览器直开时确实无 spawn(需经 web_app 启动)。

---

## 后端缺口汇总（需新建路由 — 阻塞对应 Web 真功能）
1. **/config** GET/PUT —— 设置整页落盘(最高,settings 全空转)。
2. **/recent/remove | delete_folder | clear** —— 项目管理删除。
3. **/project/overview** —— 概览聚合(manifest+pipeline+进度+next_action)。
4. **任务聚合端点** + 状态推送 —— 任务中心。
5. **ref_index 读/写 + ref 生成 + 从剧本提取实体** —— 资源库。
6. **/assets PUT/POST**(写 project.json 题材/风格) —— 编辑圣经/题材落盘。
7. **/projects/create 扩展**(写 manifest + 题材/风格向导)。
8. **/video/ltx body 扩展**(全 LTXDirectorSpec 字段) + hd_director→director_v3 映射。
9. **/split 扩展**(重采样/AI 超分)。
10. **/soundtrack advance | mixdown | accent/detect|preview | sfx/* | output | ws 播放头** + overlay 端点。
11. 逐条配音提示词持久化端点。

## 优先级路线（建议）
- **P0（先补，闭环核心创作链）**：编剧向导链编排(A 全部高优) + 拆拼裁接已有后端(C 最易) + /config 后端 + 概览/设置/任务中心后端 + 新建/打开项目链路(E 高优)。
- **P1**：导演台自由时间轴 + /video/ltx 扩展(B) + 出图参考图/任务管理 + 资源库 ref_index 后端(C/D)。
- **P2**：配乐 DAW 真功能(advance/mixdown/accent/sfx/overlay/ws — D，最重，后端缺一大片) + 导演台全参数细节。
- **P3**：转场补全、HD 超分、各占位项兑现、概览阶段口径统一、退役 PySide6。
