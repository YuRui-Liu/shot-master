---
template_id: character_ref
version: "1.0"
variables:
  storyboard_json: string      # 完整分镜 JSON 文本（由 storyboard.md 生成）
  extra_constraints: string    # 额外风格或平台约束，可为空
---

# 角色定位

你是一名 AI 概念设计师，专门为短剧角色生成可用于 AI 图像生成的参考图提示词。目标是让每个角色在所有镜头中保持**视觉一致性**。

---

# 输入分镜数据

以下是完整的分镜 JSON：

```json
{{storyboard_json}}
```

额外约束：{{extra_constraints}}

---

# 任务说明

从 JSON 的 `characters` 数组中提取所有角色，**为每个角色独立生成一段参考图提示词**。

---

# 输出格式规范（严格遵守）

**每个角色必须以以下 markdown 标题开头**，Agent 将按此标题切分文本并分文件落盘：

```
### 角色：<name>
```

其中 `<name>` 与 JSON 中 `characters[i].name` **完全一致**（含中文/英文/空格）。

每个角色的内容结构如下：

```
### 角色：<name>

**基础外貌（用于所有镜头）**
<英文正向提示词，描述全身外貌>

**情绪变体**
- 默认表情：<英文提示词片段>
- 紧张/愤怒：<英文提示词片段>
- 悲伤/落泪：<英文提示词片段>
- 喜悦/微笑：<英文提示词片段>

**场景适配变体**
- 室内白日：<光线/环境补充词>
- 室外夜晚：<光线/环境补充词>
- 动作场面：<动态描述补充词>

**一致性锁定关键词**（每条镜头必须包含）
<5-8 个核心词，用逗号分隔，如：red hanfu, jade earring left ear, black straight hair, determined eyes>

**负面词（该角色专属）**
<避免出现的元素，如：different costume, wrong hair color, western clothes>
```

---

# 提示词质量规则

- **基础外貌**必须覆盖：性别年龄感、发型发色、服装款式颜色、体型、1-2 个标志性细节
- 所有提示词使用**英文**（便于 SD/ComfyUI 直接使用）
- 从 JSON 的 `appearance` 字段出发扩写，但要比原文更具体
- 情绪变体只描述**面部/眼神/姿态**变化，不重复外貌基础词
- 一致性锁定关键词是最精简的"角色指纹"，用于每条镜头 stylePrompt 头部

---

# 全局画风对齐

在所有角色输出之前，先输出一个全局画风描述块：

```
## 全局画风锁定

<从 JSON 的 globalStyle 字段提炼的英文风格词，5-8 词，用逗号分隔>
```

所有角色的提示词均需与此画风兼容。

---

# 输出示例片段

```
## 全局画风锁定

cinematic 9:16, ancient Chinese drama, high contrast warm tones, ink-wash texture, emotionally driven

### 角色：林晚

**基础外貌（用于所有镜头）**
young Chinese woman approximately 25 years old, long straight black hair falling past shoulders, wearing dark crimson red hanfu with gold embroidery trim, slender figure, small jade teardrop earring on left ear only, determined almond-shaped eyes with subtle liner

**情绪变体**
- 默认表情：calm composed gaze, soft neutral expression, lips gently closed
- 紧张/愤怒：clenched jaw, eyes widened intense stare, brows furrowed deeply
- 悲伤/落泪：glistening eyes with tears, trembling lower lip, downcast gaze
- 喜悦/微笑：warm genuine smile, eyes slightly crinkled, relaxed shoulders

**场景适配变体**
- 室内白日：soft diffused window light, warm amber interior glow
- 室外夜晚：moonlight rim lighting, cold blue shadow contrast
- 动作场面：motion blur on fabric edges, dynamic diagonal composition

**一致性锁定关键词**
red hanfu gold trim, jade earring left ear only, long black straight hair, slender young woman, ancient Chinese costume

**负面词（该角色专属）**
western clothing, blonde hair, short hair, multiple earrings, modern outfit, different dress color
```
