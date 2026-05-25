# 翻译设置 + 提示词优化设置（独立 provider）设计

**项目**：drama-shot-master
**版本**：v0.7.x 增量（设计阶段）
**日期**：2026-05-25
**状态**：设计评审通过，待写实现 plan
**关联**：紧接 DeepLX 翻译预览、一键提示词反推优化两个已落地功能；扩展 `设置` 菜单。

---

## 1. 背景与目标

### 1.1 问题

- DeepLX 翻译只能改 `.env` 的 `DEEPLX_URL`，没有 UI 入口。
- 一键提示词反推优化复用全局 `current_provider`/`current_model`，无法为反推单独指定 API_KEY / 模型，也无法配置 meta-prompt 路径。
- 反推希望支持本地 ollama 部署的 qwen-VL 与豆包模型。

### 1.2 目标

`设置` 菜单新增两项：
1. **翻译配置** —— 配 `DEEPLX_URL`。
2. **提示词优化配置** —— 配 meta-prompt 路径 + 反推专用 provider（base_url + key + model），支持 ollama qwen / 豆包，与主反推 provider 完全解耦。

### 1.3 非目标

- 反推 provider 不支持非 OpenAI-compat 后端（gemini/anthropic 独立 SDK）
- 不用 Responses API（豆包 + ollama 都走 chat.completions）
- 翻译设置仅 `DEEPLX_URL`（不加目标语言 / 开关）
- 不做配置导入导出

---

## 2. 关键决策（评审 Q&A）

| 决策点 | 选择 | 理由 |
|---|---|---|
| refine provider | 独立一套（base_url+key+model），与 current_provider 解耦 | 用户明确要单独 key/model |
| ollama+豆包调用 | 复用现有 `openai_compat`（chat.completions + base64 图） | 零新 provider 代码；ollama 加 preset，豆包已支持 |
| refine provider 构造 | 直接 `OpenAICompatProvider(ProviderConfig(...))`，不走 registry | refine 永远是 openai-compat，registry 多余 |
| 翻译 URL 解耦 | config 值在 `load_config` / 对话框保存时同步到 `os.environ["DEEPLX_URL"]` | translator 保持 Qt-free 读 env，不必把 cfg 穿到各 widget |
| 菜单命名 | 「翻译配置…」「提示词优化配置…」 | 与现有「RunningHub 配置…」一致 |

---

## 3. 架构

| 改动 | 文件 |
|---|---|
| 新增 6 个 Config 字段 + update_settings 落盘 + load_config 读取（含 .env 兜底） | `config.py` |
| ollama preset + 加入 OPENAI_COMPAT_ENDPOINTS | `providers/factory.py` |
| 翻译设置对话框 | `ui/dialogs/translation_settings_dialog.py`（新增） |
| 提示词优化设置对话框 | `ui/dialogs/refine_settings_dialog.py`（新增） |
| `load_refine_meta_prompt(path="")` 支持自定义路径 | `core/prompt_refiner.py` |
| refine 改用独立 provider + 传 meta 路径 | `ui/panels/video_panel.py` |
| `设置` 菜单加两项 | `ui/main_window.py` |

边界：两个对话框各自独立（QDialog + cfg.update_settings）；translator 不变；prompt_refiner 仅 `load_refine_meta_prompt` 签名变。

---

## 4. 详细设计

### 4.1 config.py 新增字段

```python
# 翻译
deeplx_url: str = ""
# 帧提示词优化（refine）独立 provider
refine_base_url: str = ""
refine_api_key: str = ""
refine_model: str = ""
refine_provider_preset: str = "ollama"     # 仅 UI 下拉记忆
refine_meta_prompt_path: str = ""           # 空 = bundled 默认
```

- `update_settings` 落盘 dict 增这 6 个 key。
- `load_config`：从 settings.json 读这 6 个（`str` 类型校验）；`deeplx_url` 额外支持 `.env` 的 `DEEPLX_URL` 兜底（settings.json 未设时用 env 值）。
- `load_config` 末尾：`if cfg.deeplx_url: os.environ["DEEPLX_URL"] = cfg.deeplx_url`（让 translator 读到）。

> 注：`load_config` 需 `import os`（当前未导入）。

### 4.2 factory.py ollama preset

`openai_compat_presets()` 增：
```python
"ollama": {
    "base_url": "http://localhost:11434/v1",
    "models": ["qwen2.5-vl", "qwen2.5-vl:7b", "qwen2.5-vl:32b"],
},
```
`OPENAI_COMPAT_ENDPOINTS`（config.py）加 `"ollama"`，使 `.env` 的 `OLLAMA_API_KEY`/`OLLAMA_BASE_URL` 也能被读入（可选）。

### 4.3 translation_settings_dialog.py（新增）

```python
class TranslationSettingsDialog(QDialog):
    """设置 → 翻译配置…：配 DEEPLX_URL。"""
    def __init__(self, cfg, parent=None): ...
```
- 一个 `QLineEdit` 填 DEEPLX_URL + 说明 label（"公共实例可能不稳定，可填自部署 http://localhost:1188/translate；留空则用 .env"）
- OK：`cfg.update_settings(deeplx_url=url)`；**url 非空** → `os.environ["DEEPLX_URL"]=url`；**url 为空** → 不动 `os.environ`（保留启动时 `.env` 载入的值作为兜底）。
  - 已知小限制：若曾设过自定义 URL（已写 env）后又清空，本进程内 env 仍是旧自定义值，重启才回到 .env 值。YAGNI，不处理。

### 4.4 refine_settings_dialog.py（新增）

```python
class RefineSettingsDialog(QDialog):
    """设置 → 提示词优化配置…"""
```
字段（QFormLayout）：
- **Provider 预设** QComboBox：`Ollama (本地)` / `豆包 ARK` / `自定义`
  - 切换时自动填 base_url：ollama→`http://localhost:11434/v1`，豆包→`https://ark.cn-beijing.volces.com/api/v3`，自定义→不动
- **Base URL** QLineEdit
- **API Key** QLineEdit（Password + 👁 切换，仿 runninghub 对话框）
- **Model** QComboBox（`setEditable(True)`，预设按 provider 填建议项：ollama→qwen2.5-vl 系列；豆包→doubao 视觉模型）
- **Meta-prompt 路径** QLineEdit + 浏览按钮（留空=bundled 默认；占位符提示）
- **🔌 测试连接** QPushButton + 结果 label：后台 worker 用当前 base_url+key+model 发一个最小 `chat.completions`（纯文本 "ping"），成功显示 ✓，失败显示原因
- OK/Cancel

保存（accept）：`cfg.update_settings(refine_base_url=…, refine_api_key=…, refine_model=…, refine_provider_preset=…, refine_meta_prompt_path=…)`。校验：base_url/model 非空（key 允许空——ollama 常不需要）。

### 4.5 prompt_refiner.load_refine_meta_prompt 签名变更

```python
DEFAULT_REFINE_META_PROMPT_PATH = Path("templates/ltx_refine_meta_prompt.md")

def load_refine_meta_prompt(path: str = "") -> str:
    """path 空 → bundled 默认；否则读自定义路径。缺失 → FileNotFoundError。"""
    p = Path(path) if path else DEFAULT_REFINE_META_PROMPT_PATH
    return p.read_text(encoding="utf-8")
```
（原常量名 `REFINE_META_PROMPT_PATH` 改为 `DEFAULT_REFINE_META_PROMPT_PATH`；当前仅 prompt_refiner 内部 + 测试引用。）

### 4.6 video_panel._on_refine 改用独立 provider

```python
from drama_shot_master.providers.openai_compat import OpenAICompatProvider
from drama_shot_master.providers.base import ProviderConfig
...
def _on_refine(self):
    if not self.model.segments:
        QMessageBox.information(self, "无内容", "时间轴为空，先添加分镜段"); return
    if not self.cfg.refine_base_url or not self.cfg.refine_model:
        QMessageBox.warning(self, "未配置",
            "请先在「设置 → 提示词优化配置」填 Base URL 和 Model"); return
    provider = OpenAICompatProvider(ProviderConfig(
        api_key=self.cfg.refine_api_key or "ollama",
        base_url=self.cfg.refine_base_url,
        model=self.cfg.refine_model))
    try:
        system_prompt = load_refine_meta_prompt(self.cfg.refine_meta_prompt_path)
    except FileNotFoundError:
        QMessageBox.critical(self, "缺少 meta-prompt",
            f"找不到 meta-prompt 文件：{self.cfg.refine_meta_prompt_path or 'templates/ltx_refine_meta_prompt.md'}"); return
    req = build_refine_request(self.model)
    # …（worker / 弹窗回写逻辑不变）
```
移除原 `factory.build_provider(...)` 那段；`factory` import 若不再用可删（仍可能被其它处用——本文件只此处用 factory，可删该 import）。

### 4.7 main_window 菜单

```python
sm = menu.addMenu("设置")
a_rh = QAction("RunningHub 配置…", self); a_rh.triggered.connect(self._open_runninghub_settings); sm.addAction(a_rh)
a_tr = QAction("翻译配置…", self); a_tr.triggered.connect(self._open_translation_settings); sm.addAction(a_tr)
a_rf = QAction("提示词优化配置…", self); a_rf.triggered.connect(self._open_refine_settings); sm.addAction(a_rf)
```
两个新槽各 `XxxDialog(self.cfg, parent=self).exec()`。

---

## 5. 数据流

```
[设置 → 翻译配置] → TranslationSettingsDialog → cfg.update_settings(deeplx_url) + os.environ
        → translator.translate_en_to_zh 读 os.environ["DEEPLX_URL"]

[设置 → 提示词优化配置] → RefineSettingsDialog → cfg.update_settings(refine_*)
        → video_panel._on_refine 用 refine_* 构造 OpenAICompatProvider + load_refine_meta_prompt(path)
```

---

## 6. 错误处理

| 场景 | 行为 |
|---|---|
| refine 未配 base_url/model | _on_refine 提示去「提示词优化配置」补全 |
| meta-prompt 自定义路径不存在 | FileNotFoundError → 显示具体路径 |
| 测试连接失败（网络/鉴权/模型名错） | 结果 label 显示 ✗ + 原因，不崩 |
| DEEPLX_URL 留空 | 不写 env（保留 .env 既有值）；翻译失败时按既有"服务不可用"提示 |
| settings.json 缺新字段（老配置） | load_config 用默认值（空串），不报错 |

---

## 7. 测试

### 7.1 `tests/test_config.py` 扩展

| 用例 | 验证 |
|---|---|
| save_load_refine_fields | update_settings 写 refine_* + deeplx_url → 重新 load_config 能读回 |
| deeplx_url_env_fallback | settings.json 无 deeplx_url 但 .env 有 DEEPLX_URL → cfg.deeplx_url 或 os.environ 生效 |
| missing_new_fields_defaults | 老 settings.json（无新字段）→ load 不报错，新字段为默认空串 |

### 7.2 `tests/test_core/test_prompt_refiner.py` 扩展

| 用例 | 验证 |
|---|---|
| load_meta_default | `load_refine_meta_prompt("")` 读 bundled 默认（断言含关键标记，需 templates 文件存在） |
| load_meta_custom | tmp_path 写一个临时 md，`load_refine_meta_prompt(str(tmp))` 读到其内容 |
| load_meta_missing_raises | `load_refine_meta_prompt("/no/such.md")` → FileNotFoundError |

### 7.3 手测清单

1. 设置 → 翻译配置：填一个 DeepLX URL，保存；回 prompt 框点「译」→ 用新 URL（改成错误 URL 验证生效）。
2. 设置 → 提示词优化配置：选 Ollama 预设 → base_url 自动填 localhost:11434/v1；填 model=qwen2.5-vl；测试连接（本地 ollama 起着时 ✓）。
3. 切「豆包 ARK」预设 → base_url 自动变；填豆包 key + 视觉模型；测试连接 ✓。
4. Meta-prompt 路径留空 → 反推用内置；填一个自定义 md → 反推用它（验证可生效）。
5. 视频面板点「✨ 优化提示词」→ 用 refine 配置（不再用主反推 provider）；未配 base_url/model 时提示去设置。
6. 重启应用 → 配置持久化（settings.json）。

---

## 8. 依赖与影响面

- 零新增 pip 依赖（openai SDK 已在用）
- 新增 2 个对话框文件；改 config / factory / prompt_refiner / video_panel / main_window
- 向后兼容：老 settings.json 无新字段时取默认；refine 行为从"用全局 provider"变为"用独立配置"——首次使用需在设置里填（_on_refine 有引导提示）

---

## 9. 不做的事（YAGNI 清单）

- ❌ refine 支持 gemini/anthropic 独立 SDK
- ❌ Responses API
- ❌ 翻译目标语言 / 开关配置
- ❌ 配置导入导出
- ❌ 统一 Tab 式设置总面板（沿用每个 concern 一个独立对话框）
- ❌ 把 cfg 穿到 translate_button（走 os.environ 同步）
