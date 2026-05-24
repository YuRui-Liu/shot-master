# Prompt 中文预览 · DeepLX 接入设计

**项目**：drama-shot-master
**版本**：v0.7.x 增量功能（设计阶段）
**日期**：2026-05-24
**状态**：设计评审通过，待写实现 plan
**关联**：v0.7 视频面板已落地，prompt 字段集中在两处可编辑控件。

---

## 1. 背景与目标

### 1.1 问题

视频面板的 `local_prompt`（per-seg）与 `global_prompt`（全局）字段经常输入英文（受 LTX 等模型 prompt 习惯影响）。用户需要快速确认"这段英文翻成中文是否描述合理"，但目前需要复制到外部翻译工具，路径长。

### 1.2 目标

为两个可编辑 prompt 字段加一个"译"按钮，点击后弹窗显示中译，**完全免费、零额度限制、失败可静默回退**。

### 1.3 非目标

- 不做实时（debounce）翻译
- 不做缓存（按钮触发频次低，YAGNI）
- 不做中→英反向翻译
- 不覆盖 `inference_panel` 的结果区（首版聚焦人工编辑区）

---

## 2. 关键决策（来自评审 Q&A）

| 决策点 | 选择 | 理由 |
|---|---|---|
| 翻译服务 | DeepLX | 完全免费、无额度限制（用户要求）|
| 部署形态 | 公共实例 + 失败回退 | 零部署成本；失败时显示明确提示，不影响主功能 |
| 覆盖字段 | `segment_editor.prompt_edit` + `video_global_form.global_prompt_edit` | 两处人工编辑区，最契合"预览是否合理"的初衷 |
| 触发方式 | 手动按钮 | 避免高频调用打爆公共实例 |
| 译文呈现 | 点击后弹窗 | prompt 框已 60px 满载，无空间内联展开 |

---

## 3. 架构

### 3.1 模块拆分

```
drama_shot_master/
├── providers/
│   └── translator.py            ← 新增：纯函数 translate_en_to_zh()
└── ui/
    └── widgets/
        ├── translate_button.py  ← 新增：可复用的 attach_translate_button() 工具
        ├── segment_editor.py    ← 修改：第 42 行附近挂按钮
        └── video_global_form.py ← 修改：第 53 行附近挂按钮
```

### 3.2 边界与职责

- **`translator.py`** — 纯逻辑层，无 Qt 依赖。可单测、可在 CLI / 脚本中复用。
- **`translate_button.py`** — 纯 UI 层，把 translator 与 Qt 控件粘合。一行 `attach_translate_button(widget, parent)` 即可挂上。
- 两个 panel 文件保持现有结构，仅在创建 QLabel 时多加一行 attach 调用。

---

## 4. 详细设计

### 4.1 translator.py

```python
def translate_en_to_zh(text: str, *, timeout: float = 3.0) -> str | None:
    """
    POST 到 DEEPLX_URL，返回中译文本；任何异常返回 None。
    
    成功响应形如：{"code": 200, "data": "...", ...}
    """
```

- 读取 `os.environ.get("DEEPLX_URL")`，未配置时返回 None（且写一条 logging.warning）
- 用 `urllib.request.urlopen` + `json.dumps({"text": ..., "source_lang": "auto", "target_lang": "ZH"})`
- 超时、HTTPError、JSONDecodeError、KeyError 全部捕获后返回 None
- 不打印 stacktrace，只 `logging.info`/`logging.warning`

### 4.2 translate_button.py

```python
def attach_translate_button(
    text_widget: QPlainTextEdit,
    parent: QWidget,
) -> QToolButton:
    """
    创建并返回一个 24x24 的"译"按钮。点击时：
    1. 取 text_widget.toPlainText()；空文本则 no-op
    2. 禁用按钮，起 QThread 调 translate_en_to_zh
    3. 完成后启用按钮，弹 _TranslateDialog
    """
```

`_TranslateDialog` 是一个简单 QDialog：
- 上半 QPlainTextEdit（只读，灰底）显示原文
- 下半 QPlainTextEdit（只读）显示中译；失败时显示 `"翻译服务暂不可用。当前 DEEPLX_URL={url}"`
- 底部一行：[复制译文] [重试]（重试仅在失败态可见）[关闭]
- 非模态，可同时打开多个

### 4.3 配置

`.env.example` 追加：
```
# DeepLX 公共翻译接口（用于 prompt 中文预览）。
# 公共实例可能不稳定，可改成自部署 http://localhost:1188/translate
DEEPLX_URL=https://api.deeplx.org/translate
```

`translator.py` 内部直接 `os.environ.get("DEEPLX_URL")`，不走 `config.py`（功能单一、无需全局配置耦合）。

### 4.4 两处挂接点

**segment_editor.py 修改示意**（第 42 行附近）：
```python
prompt_label_row = QHBoxLayout()
prompt_label_row.addWidget(QLabel("Prompt"))
prompt_label_row.addStretch(1)
attach_translate_button(self.prompt_edit, self)  # ← 新增
root.addLayout(prompt_label_row)
```

> 实际实现需把按钮 add 进 prompt_label_row，而非外部布局。具体 widget hierarchy 由 plan 阶段确定。

**video_global_form.py** 同形式，第 53 行附近。

---

## 5. 数据流

```
[用户在 prompt 框输入英文]
        ↓
[点击 "译" 按钮]
        ↓
[QToolButton.disabled = True]
        ↓
[QThread → translator.translate_en_to_zh(text)]
        ↓
   ┌────┴────┐
   ✓         ✗
   ↓         ↓
[Dialog 显示译文]   [Dialog 显示"服务不可用"+ 重试按钮]
        ↓
[QToolButton.disabled = False]
```

---

## 6. 错误处理

| 场景 | 行为 |
|---|---|
| 文本为空 | 按钮 disabled（textChanged 时动态切换） |
| `DEEPLX_URL` 未配置 | translator 返回 None → 失败 dialog 提示"请在 .env 中设置 DEEPLX_URL" |
| 网络超时 (>3s) | 同上失败 dialog |
| HTTP 非 200 / JSON 解析失败 / 缺 data 字段 | 同上失败 dialog |
| 用户在请求未完成时再次点击 | 按钮已 disabled，自动屏蔽 |

---

## 7. 测试

### 7.1 单元测试 `tests/test_translator.py`

- `test_translate_success`：mock urlopen 返回 `{"code":200,"data":"你好"}` → 期望 `"你好"`
- `test_translate_timeout`：mock urlopen 抛 `socket.timeout` → 期望 `None`
- `test_translate_http_error`：mock urlopen 抛 `HTTPError` → 期望 `None`
- `test_translate_bad_json`：mock urlopen 返回非 JSON → 期望 `None`
- `test_translate_missing_data_field`：mock 返回 `{"code":500,"msg":"err"}` → 期望 `None`
- `test_translate_no_env_url`：清空 `DEEPLX_URL` → 期望 `None`

### 7.2 UI 不做自动化

PyQt 单测成本高于收益。手测清单写在 plan 里：
- 空文本时按钮变灰
- 正常翻译弹窗显示
- 断网模拟显示失败提示
- 复制按钮把中文复制到剪贴板

---

## 8. 依赖与影响面

- **零新增 pip 依赖**（只用 stdlib `urllib` + `json` + 已有的 PyQt）
- **影响文件**：`providers/translator.py`（新增）、`ui/widgets/translate_button.py`（新增）、`segment_editor.py`、`video_global_form.py`、`.env.example`
- **向后兼容**：未配置 `DEEPLX_URL` 时，按钮点击仅弹失败提示，不影响其他功能

---

## 9. 不做的事（YAGNI 清单）

- 不做翻译结果缓存
- 不做 debounce 自动翻译
- 不做多语言切换（始终 auto → ZH）
- 不覆盖 inference_panel 结果区（用户复核反馈：聚焦人工编辑区）
- 不做按钮国际化（始终显示"译"字）
