# 打包客户端（Nuitka）

## 为什么 Nuitka
PyInstaller 打的 .pyc 可被解包反编译；Nuitka 编译成原生二进制，源码不可直接还原。

## 步骤
1. `pip install nuitka`（Windows 需 MSVC/clang）。
2. 确认 `drama_shot_master/licensing/public_key.py` 已是真实公钥（见授权 plan Task 5）。
3. 运行 `build\build_client.bat`。
4. 产物在 `build/dist/main.dist/`，分发整个 `main.dist` 文件夹（多文件模式比 --onefile 杀软误报少）。

## 务必排除
- `license_admin/`（含私钥逻辑）已用 `--nofollow-import-to=license_admin` 排除。
- `license_admin/private_key.pem` 绝不进任何构建/仓库。

## 减少杀软误报（建议，非必须）
- 用代码签名证书签 `main.dist/*.exe`。
- 保持多文件模式（不要 --onefile）。

## 安全边界（务必知悉）
非对称签名杜绝 keygen/伪造、机器绑定防转发；但挡不住有人反汇编 patch 掉验签。
已做：原生编译 + 多处分散校验。目标是抬高门槛而非绝对不可破。
