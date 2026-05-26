# UI 整理：隐去反推 + 切换栏分组 — 设计

**日期**：2026-05-26
**范围**：仅 `drama_shot_master/ui/main_window.py`（及必要的纯 UI 调整）。独立于授权系统。

## 目标

1. 暂时隐去「反推」功能（保留代码，便于日后恢复）。
2. 功能切换栏由一排 6 个按钮（拥挤）改为按「图像 / 视频」分组、中间加竖分隔线，缓解拥挤。

## 现状

- `main_window.py:33` `FUNCS = [("反推","inference"),("拆图","split"),("拼图","combine"),("去白边","trim"),("视频生成","video_gen"),("配乐","soundtrack")]`
- `_build_ui` 中（约 114-122 行）用一个 `QHBoxLayout` + `QButtonGroup` 把每个 FUNCS 项渲染成可勾选按钮，索引与 `self.panels`（125-135 行）一一对应。
- 活跃面板按 **key** 持久化（`last_active_function`），不依赖索引，因此移除条目不会破坏持久化。
- `_on_func_changed(idx)` 按 `FUNCS[idx][1]` 取 key 判断 `is_wide` 等，索引对齐即可。

## 设计

### 隐去反推
- 从 `FUNCS` 移除 `("反推","inference")`（注释保留该行，并在上方留一行注释说明"暂时隐藏，恢复时取消注释并恢复 panels 对应项"）。
- 从 `self.panels` 列表移除 `InferencePanel(...)`（同样注释保留）。`InferencePanel` 源码文件**不删**。
- `__init__` 里默认勾选 index 0 的按钮仍有效（现在 index 0 = 拆图）。`last_active_function` 若历史值为 `"inference"`，`start_idx` 回退逻辑 `next(..., 0)` 已能兜底到 0（拆图），无需额外处理。
- 保留 `InferencePanel` 的 import（或一并注释）——为减少 lint 噪音，import 也注释掉，恢复时一起取消。

### 切换栏分组
把单一 `switch` 行替换为：

```
[图像：] 拆图  拼图  去白边   │   [视频：] 视频生成  配乐
```

- 仍用**一个** `QButtonGroup self.func_group`（保证全局单选互斥），`addButton(b, i)` 的 `i` 必须等于该面板在 `self.panels` 中的索引。
- 布局：外层 `QHBoxLayout`；依次加入
  - `QLabel("图像：")`
  - 图像组按钮（拆图/拼图/去白边）
  - 竖分隔线 `QFrame`（`setFrameShape(QFrame.VLine)`，`setFrameShadow(QFrame.Sunken)`）
  - `QLabel("视频：")`
  - 视频组按钮（视频生成/配乐）
  - 末尾 `addStretch(1)`，让按钮靠左不被拉伸撑满。
- 按钮创建顺序仍按 `FUNCS` 顺序遍历，但要把"该放到哪一组"用 key 判断：`split/combine/trim` → 图像组；`video_gen/soundtrack` → 视频组。`func_group.addButton(b, i)` 的 `i` 用 `enumerate(FUNCS)` 的索引。

> 分组只影响**视觉容器**，不改变 `func_group` id 与 panels 索引的对应关系。

### 组标签样式
组标签 `QLabel` 用次要色（如 `setStyleSheet("color:#9aa;")`），与现有 `exec_hint` 风格一致，避免喧宾夺主。

## 测试

- 该改动是纯布局 + 列表增删，无独立可单测的纯函数。验证方式：
  - 启动应用，确认切换栏不再出现「反推」，且呈「图像：… │ 视频：…」两组。
  - 点击每个按钮能正确切换到对应面板（拆图/拼图/去白边/视频生成/配乐），视频生成/配乐仍触发 `is_wide` 宽面板行为。
  - 关闭再打开应用，`last_active_function` 恢复正常（历史值为 inference 时回退到拆图，不报错）。
- 若 `last_active_function` 持久化为 `"inference"` 的回退路径希望加保护，可在 `__init__` 中把目标 key 为 `"inference"` 时显式置为 `"split"`（可选，`next(...,0)` 已兜底）。

## 非目标

- 不改 panels 本身的内部布局。
- 不删除 `InferencePanel` 源文件或其测试。
