# 设置对话框 设计规格

**项目代号**：shot-prompt-backwards v0.4
**日期**：2026-05-17
**状态**：设计评审中（待用户审阅 spec）
**前置版本**：v0.3（PySide6 三栏统一界面）

---

## 1. 背景与目标

v0.3 重构时删掉了 v0.2 的 settings tab，导致**没有任何 UI 入口**配置后端/模型/API Key/默认反推模板。当前：
- provider/model 只能改 settings.json 或靠 .env 默认
- API Key 只从 .env 读，不能在 UI 改、不持久化
- 反推模板每次启动回到列表第一个，无"默认模板"记忆

**目标**：菜单栏「设置」→ 模态对话框，集中配置后端 provider/model、各 provider API Key、默认反推模板，全部记忆到 settings.json，避免每次启动重设。

---

## 2. 范围

### 2.1 In Scope

- 菜单栏新增「设置」菜单 → 「首选项…」→ 弹出 `SettingsDialog`
- 对话框 3 组：后端（provider+model+测试连通）/ API Key（每 provider 一行）/ 默认反推模板
- `config.py` 持久化白名单扩展：加 `api_keys`、`default_template`
- API Key 合并策略：.env 仍读（兼容），settings.json 同名 key 覆盖
- 两层模板记忆：设置框选"默认模板"存 settings.json；反推面板本会话临时切记内存
- 测试连通：后台 QThread 1×1 像素图调 provider，结果显对话框内
- 落地方式：方案 A（单对话框分组 QGroupBox 竖排）

### 2.2 Out of Scope

- 不动 v0.3 的三栏 panel 架构（设置不进 BasePanel）
- 不做 settings.json 加密（明文 + .gitignore 已覆盖）
- 不做 provider/key 的删除 UI（留空=不动，删除去手改文件）
- 不改 .env 文件本身（只读，不回写）
- 不做 pytest-qt（UI 层 py_compile + 手动 smoke）

---

## 3. config.py 持久化改造

### 3.1 Config dataclass 新增字段

```python
default_template: Optional[str] = None   # 反推默认模板 id
```

（`api_keys` / `current_provider` / `current_model` 字段已存在，无需新增）

### 3.2 update_settings 落盘白名单扩展

当前硬编码 5 字段，扩为 7：

```python
data = {
    "current_provider": self.current_provider,
    "current_model": self.current_model,
    "ui": self.ui,
    "last_input_dir": self.last_input_dir,
    "last_output_dir": self.last_output_dir,
    "api_keys": self.api_keys,            # 新增
    "default_template": self.default_template,  # 新增
}
```

### 3.3 load_config 读取 + key 合并策略

- `.env` 仍按现有逻辑读 api_keys/base_urls（向后兼容）
- 读 settings.json 后：
  - `api_keys`：settings.json 的 key **合并覆盖**到 .env 读来的同名 key（`cfg.api_keys.update(data["api_keys"])`，UI 改的优先）
  - `default_template`：直接 `cfg.default_template = data["default_template"]`
- 安全：settings.json 含明文 key，已在 .gitignore（v0.2 已加 `settings.json`），无需额外处理

---

## 4. SettingsDialog 结构

新建 `app/ui/settings_dialog.py`，`SettingsDialog(QDialog)` 竖排 3 个 QGroupBox：

```
┌─ 设置 ───────────────────────────────────┐
│ ┌─ 后端 ────────────────────────────┐   │
│ │ Provider [doubao          ▾]      │   │
│ │ Model    [doubao-seed-2-0-… ▾]    │   │  provider→model 联动
│ │          [🔌 测试连通]  状态label │   │
│ └───────────────────────────────────┘   │
│ ┌─ API Key ─────────────────────────┐   │
│ │ gemini    [••••••••]               │   │  factory 已知 provider
│ │ doubao    [••••••••]               │   │  每行 password QLineEdit
│ │ anthropic [        ]               │   │  已有值预填
│ │ … openai/deepseek/qwen/…          │   │
│ └───────────────────────────────────┘   │
│ ┌─ 默认反推模板 ────────────────────┐   │
│ │ [多帧自适应 (multi_frame) ▾]      │   │  扫 templates/*.md
│ └───────────────────────────────────┘   │
│              [测试连通] [保存] [取消]    │
└──────────────────────────────────────────┘
```

### 4.1 后端组

- provider 下拉 = 扁平 9 项：复用 factory 枚举（独立 provider gemini/anthropic/qwen + openai_compat_presets 展开 openai/deepseek/doubao/openrouter/siliconflow/vllm）
- 选 provider → model 下拉刷新（独立 provider 用 `cls.available_models()`；compat endpoint 用 `preset["models"]`）
- 「测试连通」：FunctionWorker 后台，1×1 像素 PNG 调 `provider.generate`，结果显组内 label（不弹窗、不冻 UI）

### 4.2 API Key 组

- 遍历 factory 已知 provider 名，每个一行 `QLineEdit(EchoMode.Password)`
- cfg.api_keys 已有该 key → 预填（password 回显）
- **留空不覆盖语义**：保存时只把**非空**框写入 cfg.api_keys；空框 = 保留该 provider 现有 key（防手滑清空）

### 4.3 默认模板组

- `list_templates(Path("templates"))` 填下拉，当前选中 = cfg.default_template（无则列表第一个）

### 4.4 保存 / 取消

- 保存：收集三组 → `cfg.update_settings(current_provider=, current_model=, api_keys=, default_template=)` 原子写 → dialog.accept()
- 取消：dialog.reject()，不写
- settings.json 写失败（权限）→ QMessageBox.critical，不关对话框

---

## 5. MainWindow 接线 + 启动联动

### 5.1 菜单

`_build_ui` 现有 `文件` 菜单旁加：

```python
sm = menu.addMenu("设置")
a_settings = QAction("首选项…", self)
a_settings.triggered.connect(self._open_settings)
sm.addAction(a_settings)
```

### 5.2 _open_settings

```python
def _open_settings(self):
    dlg = SettingsDialog(self.cfg, parent=self)
    if dlg.exec():
        self.status.setText(
            f"后端: {self.cfg.current_provider} · {self.cfg.current_model}")
        self.panels[0].apply_default_template()
```

### 5.3 InferencePanel 两层模板记忆

- `_reload_templates()` 末尾：若 `cfg.default_template` 在列表里 → combobox 默认选它
- 新增 `apply_default_template()`：设置框改完后 MainWindow 调它跳到新默认
- 面板内用户临时切模板 → 存实例变量 `_session_last_template`（不落盘）
- 优先级：本会话临时选 > cfg.default_template > 列表第一个
- 关闭软件后 `_session_last_template` 丢失，下次启动回 cfg.default_template

---

## 6. 错误处理

| 场景 | 行为 |
|---|---|
| provider 无 key 点测试连通 | label 红字"缺少 API Key"，不调 API |
| 测试连通 API 报错 | label 红字显示错误首行，对话框不关 |
| settings.json 写失败（权限） | QMessageBox.critical，保存不关对话框 |
| default_template 指向已删模板 | 启动回退列表第一个，不报错 |
| api_keys 框全空保存 | 允许（=不改 key），正常关 |

---

## 7. 测试策略

- **纯逻辑单测**（`tests/test_config.py` 扩充）：
  - `default_template` 持久化往返
  - `api_keys` 持久化往返
  - settings.json 的 api_keys 覆盖 .env 同名 key 优先级
- **UI 层**（settings_dialog.py / main_window.py 改动）：py_compile + 手动 smoke
- 现有 62 测试保持全绿

### 7.1 验收标准

- [ ] 菜单栏「设置」可见，点开弹对话框
- [ ] 改 provider/model/key/默认模板 → 保存 → 重开软件设置还在
- [ ] settings.json 的 key 覆盖 .env 同名 key
- [ ] 测试连通后台跑不冻 UI，结果显对话框内
- [ ] 反推面板启动默认选 cfg.default_template；本会话临时换不影响下次启动默认
- [ ] key 框留空保存 = 不清空已有 key
- [ ] 现有 62 + 新增 config 测试全绿

---

## 8. 文件清单

```
新建:
  app/ui/settings_dialog.py        # SettingsDialog 对话框

修改:
  app/config.py                    # +default_template 字段；持久化白名单+api_keys/default_template；load 合并 api_keys
  app/ui/main_window.py            # +设置菜单 +_open_settings
  app/ui/panels/inference_panel.py # +cfg.default_template 默认选中 +apply_default_template +_session_last_template
  tests/test_config.py             # +3 测试

保留不动:
  app/ui/state.py / geometry.py / thumbnail_*.py / preview_dialog.py / panels/{base,split,combine,trim}
  app/grid_ops.py / core/ / providers/
```

---

## 9. 风险

| 风险 | 应对 |
|---|---|
| settings.json 明文 key 泄露 | 已在 .gitignore（v0.2 加过）；对话框 password 回显 |
| factory provider 枚举与 v0.2 ping 逻辑断裂 | factory 接口稳定（list_providers/openai_compat_presets）；ping 逻辑从 v0.2 git 历史 git show 复用 |
| config 持久化改动破坏现有 62 测试 | api_keys/default_template 是新增白名单项，不影响现有字段；test_config 扩充覆盖 |
| 留空 key 误清空 | 设计明确"非空才写入" |

---

## 10. 下一步

1. 用户审阅本 spec
2. 通过后 → writing-plans 出实现计划
3. subagent-driven 执行
