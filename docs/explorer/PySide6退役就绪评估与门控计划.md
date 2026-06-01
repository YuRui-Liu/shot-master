# PySide6 退役就绪评估与门控计划

> 2026-06-01。结论先行：**现在不能退役 PySide6**。退役是不可逆、影响全局的操作；当前 Web 层全部改动只过了 JS 语法 + 后端单测，**零次真机端到端验证**。PySide6 是唯一已验证可用的版本，是回退安全网。本文给出退役的**门控条件 + 分步计划**，满足后再退。

## 1. 为什么现在退役是错的
- **绞杀者模式的前提是"先 parity，后退役"**（见 [[gui-web-rewrite-strategy]] M6）。当前未达 parity：Web 各页大量是"刚接活/刚改 bug"，未经真机验证。
- **无真机 e2e**：所有提交都是 `node --check` JS 语法 + pytest 单测；没有一次 `web_app.py` 真机跑通完整链路（出图需 provider key、视频/配音需选项目+RunningHub）。
- **退役不可逆**：删/停 PySide6 入口后，一旦 Web 某环节真机不通，用户无可用版本。
- **两入口并存成本低**：`python -m drama_shot_master.main`(PySide6) 与 `python web_app.py`(Web) 已并存且互不干扰，保留 PySide6 几乎零维护成本，却保住回退能力。

## 2. 退役门控条件（全部满足才退）
按子系统逐项**真机 e2e 通过**（在 web_app.py 壳内，对真实项目如 P-003）：
| 子系统 | 门控验收项 |
|---|---|
| 启动/壳 | web_app 启动直达 UI、无边框标题栏、窗控、任务中心、文件选择桥真机可用 |
| 首页/概览 | 新建/打开项目、概览扫真实产物显示阶段、最近产物 |
| 编剧链 | 立意续聊+选定+归档切回、剧本分集生成+落盘、分镜生成+落盘、出图prompt；二次打开全回显 |
| 资源库 | ref 三类读写、从剧本提取、生成 ref(风格锁三视图)、查看灯箱 |
| 分镜板 | 分镜视角接真实分镜+出图(参考图/预置词)、自由模式拆拼裁+输入/输出目录+刷新 |
| 视频生成 | 模式1导演台时间轴提交(16:9不截断)、模式2对齐真实分镜、query_task SSL重试、code=805 排清 |
| 配音 | 模式1自由配音(音色设计/克隆/情感)、模式2分镜对齐，真机出音 |
| 配乐DAW | 视频预览+LLM对话识别情绪→overlay生成BGM/SFX、4固定轨、advance/mixdown/accent 真机出片 |
| 转场 | 列目录/缩略图/trim/analyze/render 真机成片 |
| 设置 | /config 落盘回显、RunningHub/LLM 测试连接真机通、各 workflow_id |
- 附加：性能/内存可接受；关键路径无崩溃；用户主观验收"Web 可完全替代日常使用"。

## 3. 分步退役计划（门控通过后）
1. **冻结期**：宣布 Web 为默认入口，PySide6 标"legacy 仅回退"，观察 1-2 周真机使用无阻断。
2. **依赖切割**：确认后端(agents/core/providers/imaging/services/licensing/screenwriter_agent/sound_track_agent/media_agent)**不依赖** PySide6；仅 `drama_shot_master/ui/*`(PySide6 UI 层 ~24k LOC) 是待退役部分。Web 壳 web_host.py 仍用 QtWebEngine(PySide6 的 QtWebEngineWidgets)——**注意：退役 PySide6 UI ≠ 退役 Qt**，QtWebEngine 仍是当前 Web 壳运行时(终态若转 pywebview/Tauri 才彻底去 Qt)。
3. **退役动作**(可逆分级)：
   - L1：入口下线——`python -m drama_shot_master.main` 加 deprecation 提示/默认转 web_app；不删代码。
   - L2：移动 `drama_shot_master/ui/`(纯 PySide6 面板,非 web_host) 到 `legacy/` 目录，保留 git 历史。
   - L3：删除 legacy UI 代码与其专属测试（确认无 import 牵连后）。
4. **终态壳决策(可推迟)**：QtWebEngine → pywebview/Tauri(小包体)，与退役 PySide6 UI 解耦，单独评估。

## 4. 当前建议动作（本阶段就能做、零风险）
- **不执行退役**。先把"真机冒烟"做起来：建一份 `真机冒烟验收清单.md`(即 §2 表)，每完成一个子系统真机验证就打勾。
- 待清单全绿 → 执行 §3 L1(入口提示)，再逐级 L2/L3。
- 在此之前，PySide6 与 Web 并存不动。

## 结论
退役 PySide6 是**有价值的终点**，但**前置条件是真机 parity**，现在不具备。建议：继续补齐 Web 真机验证（最高优先：你本来就在做的逐项真机反馈循环），用 §2 清单驱动；全绿后按 §3 分级可逆退役。**现在不删任何 PySide6 代码。**
