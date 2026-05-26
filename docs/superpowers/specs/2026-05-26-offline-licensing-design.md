# 离线授权系统 + 关于/激活 + 打包 — 设计

**日期**：2026-05-26
**范围**：新增客户端 license 核心、关于/激活对话框、独立管理端工具、Nuitka 打包配置。
**目标**：防止软件被随便盗版——杜绝 keygen 伪造、阻止激活码跨机器转发，并把源码隐藏起来。

## 决策（已与用户确认）

- 校验模式：**全离线 + 非对称签名**（管理端持私钥签发，客户端内置公钥验签，无服务器、可离线）。
- **机器绑定**：激活码绑定到具体电脑的机器码，仅在该机生效。
- 默认有效期 **90 天**（管理端生成时可逐个调整）。
- 到期行为：**到期前 7 天预警 + 过期硬阻断**（过期后主功能不可用，必须输入新码）。
- 客户端打包：**Nuitka**（编译原生二进制，不泄露源码）。
- 管理端：**迷你 PySide6 GUI**（输入机器码 + 有效期 → 一键出码）。

## 诚实的安全边界（写入文档，避免误期望）

非对称离线签名**能**做到：没有私钥就造不出任何有效激活码（杜绝 keygen）；机器绑定使一个码无法转发给别的电脑。**不能**做到：阻止铁了心的攻击者反汇编某个二进制、把"验签调用"patch 掉。我们的目标是**把破解门槛抬到高于普通用户的盗版意愿**——用 Nuitka 原生编译 + 多处分散校验 + 完整性校验提高成本，而非追求绝对不可破（对小厂不划算）。

## 架构总览

```
[管理端 license_admin/ (你保管，绝不发布)]
   持私钥 ── 输入机器码+有效期 ──签名──▶ 激活码字符串
                                              │ 用户复制/粘贴
[客户端 drama_shot_master/]                    ▼
   licensing/ 核心 ── 内置公钥 ──验签+校验机器码+校验未过期──▶ 通过/拒绝
       ▲                                          │
   关于/激活对话框 (UI 入口)              门禁：未通过则禁用主界面
```

三个独立单元：①客户端 `licensing/` 核心（纯逻辑，可单测）；②关于/激活 UI（调用①）；③管理端 GUI（独立程序，调用与①共享的 token/crypto 逻辑）。

## 单元 1：客户端 license 核心 `drama_shot_master/licensing/`

职责：算机器码、验签激活码、判定授权状态、持久化。**不依赖 PySide6**，可 headless 单测。

### 文件
- `fingerprint.py` — 机器码。
- `token.py` — 激活码的编解码 + 验签（公钥侧）。
- `public_key.py` — 内置 Ed25519 公钥（32 字节，base64 常量）。
- `manager.py` — 授权状态机 + 持久化（读写已激活的码、判定 state）。

### `fingerprint.py`
- `machine_id() -> bytes`：返回 10 字节稳定机器指纹。
  - Windows：读注册表 `HKLM\SOFTWARE\Microsoft\Cryptography\MachineGuid`（OS 安装时生成，极稳定，仅重装系统才变；硬件更换不变——调研结论）。`SHA256(MachineGuid.encode()).digest()[:10]`。
  - 非 Windows（开发机/CI）：回退到 `~/.drama_shot_master/dev_machine_id`（首次随机生成并落盘），保证开发期可用。
- `machine_code() -> str`：把 `machine_id()` 编成人类可读的分组 base32（如 `ABCD-EF12-3456-7890`），供用户复制发给厂商。
- 单一稳定因子（MachineGuid）即可，**不做多因子容差**（YAGNI；MachineGuid 已足够稳定，未来需要再加）。

### `token.py`（编解码 + 验签）
- 激活码 payload（紧凑二进制，`struct` 打包）：
  - `version: uint8`（=1）
  - `machine_id: 10 bytes`（绑定的机器码）
  - `expiry: uint32`（到期日，Unix epoch **天数**=`epoch_seconds // 86400`，省字节）
  - `license_id: uint32`（授权流水号，便于你登记是谁的码）
  - 合计 1+10+4+4 = 19 字节。
- 签名：`Ed25519` 对 payload 签名 → 64 字节。
- 激活码字符串 = `base32(payload(19) || sig(64))`，去掉 `=` 填充，每 4 字符插一个 `-` 便于阅读/粘贴（≈133 字符，**面向粘贴而非手敲**）。
- 客户端函数：
  - `decode(code_str) -> (payload_fields, sig) | raise InvalidToken`
  - `verify(code_str, public_key) -> VerifiedLicense | raise InvalidToken`：先验签（签名不符即拒），再解出 machine_id/expiry/license_id。**只验签，不在此判机器匹配/过期**（交给 manager，便于分别给出"非本机/已过期"提示）。
- 防篡改：任何对 payload 的改动都会使 Ed25519 验签失败 → `InvalidToken`。

### `manager.py`（状态机 + 持久化）
- 已激活的码存到配置目录 `~/.drama_shot_master/license.txt`（纯激活码字符串）。
- `status() -> LicenseStatus`：枚举 `UNACTIVATED / VALID / EXPIRED / WRONG_MACHINE / TAMPERED`，附 `expiry_date` 与 `days_left`。
  - 读 license.txt → `token.verify` → 比对 `machine_id()` 是否等于 payload.machine_id（不等 = WRONG_MACHINE）→ 比对 expiry 与今天（过期 = EXPIRED）→ 否则 VALID。
  - 验签失败 = TAMPERED；文件不存在 = UNACTIVATED。
- `activate(code_str) -> LicenseStatus`：校验通过才写入 license.txt；否则不写并返回失败原因。
- `days_left()` 用于"到期前 7 天预警"。

## 单元 2：关于 / 激活 UI

### 菜单
- `main_window.py` 菜单栏「设置」旁新增顶级菜单「关于」，`QAction("关于…")` → 打开 `AboutDialog`。

### `AboutDialog`（新 `drama_shot_master/ui/dialogs/about_dialog.py`）
- **开发者信息区**：应用名、版本号（读 `importlib.metadata.version("drama-shot-master")`，失败回退常量）、版权 `© 2026 <作者>`、联系方式（占位，用户后续填）。
- **授权状态区**：根据 `manager.status()` 显示
  - VALID：`已激活，有效期至 2026-08-24（剩 81 天）`，绿色。
  - EXPIRED/UNACTIVATED/WRONG_MACHINE/TAMPERED：红色提示对应文案。
- **机器码区**：只读显示 `machine_code()` + 「复制机器码」按钮。
- **激活区**：多行输入框（粘贴激活码）+「激活」按钮 → 调 `manager.activate()`；成功提示并刷新状态区，失败弹出原因。

## 门禁（启动与运行期）

- `main()`（`drama_shot_master/main.py`）创建 `MainWindow` 前先查 `manager.status()`：
  - 非 VALID → 弹**模态激活门**对话框（复用/特化 AboutDialog，激活区为主，**不能跳过进入主界面**；可"退出"）。激活成功后才继续进主界面。
- 进入主界面后：
  - 若 `days_left() <= 7`：顶部状态栏/启动时一次性非阻断提醒"授权将于 X 天后到期"。
  - 运行期每天（`QTimer`，间隔 24h，或每次窗口激活时）复查 `status()`；变为 EXPIRED 时弹激活门并禁用主功能。
- **分散校验**（抬高破解成本）：除启动门禁外，在 ≥2 个关键动作入口（如"视频生成提交"、"执行"按钮）再各做一次轻量 `status()==VALID` 断言；任一处失败即拦截。避免单一 choke point 被一刀 patch。

## 单元 3：管理端 `license_admin/`（独立程序，绝不随客户端发布）

- 独立顶层包/目录，**不在客户端 Nuitka 构建范围内**，也不进客户端 wheel。
- `keygen.py`：一次性生成 Ed25519 密钥对。
  - 私钥写 `license_admin/private_key.pem`（你离线保管，**永不进 git、永不进客户端**）。
  - 打印公钥 base64，供手动粘贴进客户端 `licensing/public_key.py`。
- `admin_gui.py`（迷你 PySide6 窗口）：
  - 输入：机器码（粘贴用户发来的 `ABCD-EF12-...`）、有效期天数（默认 90）、授权流水号（可自增/手填）。
  - 动作：用私钥按 `token.py` 同款格式签发 → 显示激活码 + 「复制」按钮。
  - 维护一个本地 `issued.csv`（机器码/流水号/到期/签发时间），便于你登记与排查。
- token 编解码逻辑与客户端**共用同一份实现**：把 `token.py` 的纯编解码部分做成不含公私钥的中立模块，客户端只用"验签"，管理端只用"签发"。

> 注意：`private_key.pem` 必须加入 `.gitignore`，绝不提交。

## 单元 4：打包（Nuitka）

- 用 **Nuitka** 编译客户端为 Windows 原生二进制（`--standalone`，多文件模式而非 `--onefile`，减少杀软误报）；`--enable-plugin=pyside6`。
- **排除** `license_admin/`、`tests/`、spec/plan 文档进入构建产物。
- 公钥作为常量内置；私钥绝不进客户端。
- 建议（文档记录，非本期强制）：代码签名证书以降低 Windows Defender 误报；可选 Nuitka Commercial 加密常量/反调试。
- 产出一个可复用的构建脚本/命令（记录在 `docs/` 或 `build/` 下），含确切 Nuitka 参数。
- 构建产物体积大、构建慢属预期。

## 测试

纯逻辑单测（headless，不需 GUI、不需真实私钥——测试内临时生成一对密钥）：
- `token` 签发→验签**往返**成功。
- 篡改 payload 任一字节 → 验签失败（TAMPERED）。
- 过期日期 → status=EXPIRED；未来日期 → VALID。
- 机器码不匹配 → WRONG_MACHINE。
- `manager.activate` 成功才落盘；失败不写文件。
- `fingerprint.machine_id()` 在同机多次调用稳定一致（mock 注册表/dev 文件）。
- 管理端签发的码能被客户端验签通过（两侧格式一致性）。
- 激活码字符串 round-trip（编码→解码）稳定。
门禁/对话框为薄 UI 层，靠手动验证：未激活→启动被拦；输入有效码→进入；改系统时间使其过期→再次被拦。

## 落地顺序（writing-plans 阶段细化）

1. `licensing/` 纯核心（fingerprint/token/manager）+ 单测。
2. 管理端 `license_admin/`（keygen + GUI）+ 用它生成一对真密钥、把公钥填入客户端。
3. 关于/激活对话框 + 启动门禁 + 分散校验。
4. Nuitka 构建脚本 + 文档。

## 非目标

- 不做在线服务器/实时吊销（已选离线模式）。
- 不做多因子机器指纹容差（v1 用 MachineGuid 单因子）。
- 不追求绝对防破解（见"安全边界"）。
