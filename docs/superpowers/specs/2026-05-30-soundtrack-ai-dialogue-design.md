# 配乐 AI 对话面板（类 ACE Video Composer）设计 — 子项目 #1

> 日期：2026-05-30　分支：main
> 5 个对标 ACE 子项目的第 1 个。后续：#2 轨级混音控件 / #3 选区局部生成 / #4 Stem 导出 / #5 片段淡入淡出。

## 背景与定位

对标 ACE Studio `Video Composer` 的右侧 AI 对话面板。当前 [配乐] 用任务的 `style` 单字段 + vision 情绪标注 + 纯模板 `compose_music_prompt` 生成各段 BGM prompt，缺自然语言对话式整体调控与多轮迭代。

本子项目加一个**对话式配乐方向控制层**：用户用自然语言描述/修改配乐 → 文本 LLM 归并成结构化「配乐方向」→ 写入各段 `music_prompt`（**不自动生成，不烧 RunningHub 积分**）→ 用户在 Inspector 看新 prompt、自行点生成。

## 已锁定的决策

- **深度 C**：首版做 A（全局对话），数据结构为 B（分段指令）预留接口，后续平滑升级。
- **1a**：发指令只更新「方向 + 各段 prompt」，**不自动生成**。
- **2y**：每轮用文本 LLM 把对话归并成结构化配乐方向（处理"再快点"这类覆盖修正）。
- **单会话**：每任务一条对话历史，持久化进 session.json。
- **布局方案 A**：右栏上下分栏 —— 上半 AIChatPanel（常驻），下半 Inspector（选中 cue 显示属性）。

## 数据模型

新增 `sound_track_agent/session.py`：

```python
@dataclass
class SoundtrackDirective:
    global_directive: str = ""                       # 归并后的全局配乐方向
    segment_directives: dict[int, str] = {}          # B 预留：段index→分段方向（首版空）
    conversation: list[dict] = []                    # [{"role":"user|assistant","text":...}]
    def to_dict(self)/from_dict(cls,d)               # 同其它 dataclass

# ScoringSession 加字段：
    directive: SoundtrackDirective = field(default_factory=SoundtrackDirective)
```

`ScoringSession.to_dict/from_dict` 增补 `directive` 序列化（缺省空 directive，向后兼容旧 session.json）。

## 后端：方向归并（文本 LLM）

新增 `sound_track_agent/directive_composer.py`：

```python
def synthesize_directive(provider, current: SoundtrackDirective,
                         instruction: str, n_segments: int) -> SoundtrackDirective:
    """给定当前方向 + 历史对话 + 新指令 → 文本 LLM 输出更新后的方向。

    LLM 提示要点：
    - 输入：当前 global_directive + conversation 摘要 + 新 instruction + 段数
    - 输出 JSON：{ "global": "...", "segments": {"1":"...", ...}, "reply": "一句变更摘要" }
    - 规则：新指令是「修正/覆盖」而非「追加」时，正确覆盖旧设定（如"舒缓"→"再快点"则覆盖为快）
    - 首版只要求产出 global（segments 可空，B 预留）
    返回新 SoundtrackDirective（conversation 追加 user 指令 + assistant reply）。
    """
```

- LLM provider：复用文本 `OpenAICompatProvider`（同 deepseek/refine 配置；新增 `_build_text_provider(cfg)` 取 `soundtrack_model`/`refine_model` + 对应 key/base_url）。
- 网络调用 → 由 UI 层放进 `FunctionWorker`，不阻塞主线程。
- 纯函数可测：注入 fake provider（返回固定 JSON）验证 conversation 追加 + 覆盖逻辑 + JSON 解析容错（非法 JSON → 保留旧 global + reply 报错提示，不崩）。

## 后端：方向 → 各段 prompt

新增 facade 入口 `sound_track_agent/facade.py`：

```python
def apply_directive_to_prompts(session: ScoringSession) -> None:
    """把 session.directive 写入各段 music_prompt（纯模板重算，不联网、不生成）。

    - effective_style(seg) = directive.segment_directives.get(seg.index)
                             or directive.global_directive
                             or session.global_style
    - seg.music_prompt = compose_music_prompt(effective_style, seg.emotion, seg.shot_duration)
    - 同步 session.global_style = directive.global_directive（非空时），保持单一可信源
    - 不触发 RunningHub；不改 candidates/chosen
    """
```

复用现有纯模板 `prompt_composer.compose_music_prompt`。各段 `emotion` 已有则带情绪曲线；无则模板退化为纯 global。可单测（构造 session + directive → 断言 music_prompt 含 global 关键词）。

## UI：AIChatPanel

新增 `drama_shot_master/ui/widgets/soundtrack_ai_chat.py`：

```python
class AIChatPanel(QWidget):
    # 用户发指令请求：text=指令，apply_prompts=是否写入各段 prompt
    directiveRequested = Signal(str, bool)   # (instruction, apply_prompts)

    def set_directive(self, directive)       # 渲染对话历史 + 当前方向块
    def set_busy(self, on: bool)             # "AI 思考中…" + 禁用输入
    def append_error(self, msg: str)
```

四块（见 `docs/explorer/ai-chat-panel-layout.html`）：
1. **会话区**：QScrollArea 气泡列表（user 右蓝 / assistant 左灰），渲染 `directive.conversation`。
2. **当前配乐方向**：只读块显示 `global_directive`（+ 分段方向，B 预留）。
3. **输入框 + 双按钮**：「仅更新方向」→ `directiveRequested(text, False)`；「更新并查看 prompt」→ `directiveRequested(text, True)`。
4. （联动）更新后由编辑器刷新 Inspector。

## UI：SoundtrackEditor 布局接线

`drama_shot_master/ui/widgets/soundtrack_editor.py`：
- 右栏 `_inspector_container`（现 280px 纯 Inspector）改为 `QSplitter(Qt.Vertical)`：上 = `AIChatPanel`，下 = Inspector 容器。宽度保持 ~300px。
- `__init__` 建 `self._ai_chat = AIChatPanel(self)`，载入 `session.directive`。
- 接 `self._ai_chat.directiveRequested.connect(self._on_directive_requested)`。
- 新方法：

```python
def _on_directive_requested(self, instruction: str, apply_prompts: bool):
    if self._session is None:
        self._ai_chat.append_error("尚无 session，请先「开始配乐」生成段落。")
        return
    if self._dir_worker is busy: return
    self._ai_chat.set_busy(True)
    provider = build text provider; cur = session.directive; n = len(segments)
    def task():
        from sound_track_agent import directive_composer, facade
        new_dir = directive_composer.synthesize_directive(provider, cur, instruction, n)
        return new_dir
    worker.finished → self._on_directive_built(new_dir, apply_prompts)

def _on_directive_built(self, new_dir, apply_prompts):
    self._session.directive = new_dir
    if apply_prompts:
        facade.apply_directive_to_prompts(self._session)
    self._persist_session()
    self._ai_chat.set_directive(new_dir)
    self._ai_chat.set_busy(False)
    self._refresh_inspector()     # 各段 prompt 已变 → Inspector 反映
    self._refresh_track_view()
```

## 数据流

```
用户输入指令 ─→ AIChatPanel.directiveRequested(text, apply?)
   ─→ FunctionWorker: directive_composer.synthesize_directive(文本LLM)
        ─→ 新 SoundtrackDirective（global + conversation 追加）
   ─→ session.directive = new；apply? → facade.apply_directive_to_prompts（纯模板写各段 music_prompt）
   ─→ 持久化 session.json；刷新 AIChatPanel + Inspector
   ※ 全程不触发 RunningHub 生成（生成仍走原「开始配乐 / 生成」按钮）
```

## 错误处理

- LLM 网络失败 / 非法 JSON → worker.failed 或 composer 内部容错 → `AIChatPanel.append_error`，保留旧 directive，输入框可重试。
- 无 session → 提示先生成段落，不调 LLM。
- 旧 session.json 无 directive 字段 → from_dict 给空 directive，正常加载。
- 文本 provider 配置缺失（无 key）→ append_error 提示去设置填配乐/refine 模型。

## 测试策略

- `SoundtrackDirective` to_dict/from_dict round-trip；ScoringSession 含/不含 directive 的兼容加载。
- `synthesize_directive`（fake provider）：首轮产出 global + conversation 追加；覆盖修正（"舒缓"后"再快点" → global 体现快）；非法 JSON → 不崩、保留旧 global。
- `apply_directive_to_prompts`：directive.global 写入各段 music_prompt + session.global_style；segment_directives 优先于 global（B 预留路径）。
- `AIChatPanel`（offscreen）：构造；set_directive 渲染 N 条气泡；双按钮分别 emit (text, False)/(text, True)；set_busy 禁用输入。
- 编辑器接线 smoke：`_on_directive_requested` 无 session → error 不崩；`_on_directive_built` apply=True → 各段 music_prompt 变 + Inspector 刷新（mock worker 同步返回）。

## 不做（YAGNI，留后续子项目）

- 多会话 / 多版方案对比（ACE #4.6）—— 后续子项目。
- 分段指令解析的 LLM 自动定位（B 的完整实现）—— 数据结构已留，逻辑后做。
- 风格强度滑块（情绪/节奏复杂度/乐器）—— 可选，不在 #1。
- 自动生成（烧积分）—— 明确由用户手动触发。

## 文件清单

```
新增:
  sound_track_agent/directive_composer.py            # synthesize_directive
  drama_shot_master/ui/widgets/soundtrack_ai_chat.py # AIChatPanel
  tests/test_sound_track_agent/test_directive_composer.py
  tests/test_sound_track_agent/test_apply_directive.py
  tests/test_ui/test_ai_chat_panel.py
  tests/test_ui/test_soundtrack_ai_wiring.py

改:
  sound_track_agent/session.py        # SoundtrackDirective + ScoringSession.directive
  sound_track_agent/facade.py         # apply_directive_to_prompts
  sound_track_agent/provider.py       # _build_text_provider（文本对话 provider）
  drama_shot_master/ui/widgets/soundtrack_editor.py  # 右栏垂直分栏 + AI 接线
  tests/test_sound_track_agent/test_session.py        # directive 兼容
```
