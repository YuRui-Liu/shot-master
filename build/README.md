# 打包客户端（Nuitka）

## 为什么 Nuitka
PyInstaller 打的 .pyc 可被解包反编译；Nuitka 编译成原生二进制，源码不可直接还原。

## 步骤
1. `pip install nuitka`（Windows 需 MSVC/clang）。
2. 确认 `drama_shot_master/licensing/public_key.py` 已是真实公钥（见授权 plan Task 5）。
3. 运行 `build\build_client.bat`。
4. 产物在 `build/dist/main.dist/`，分发整个 `main.dist` 文件夹（多文件模式比 --onefile 杀软误报少）。

## 打包内容（随代码增长更新）
- `drama_shot_master`（GUI）+ `screenwriter_agent`（编剧 Agent）+ `sound_track_agent`（配乐）三个顶层包。
- 提示词模板：`drama_shot_master/templates`（LTX 工作流 json/yaml）+ `screenwriter_agent/templates`（创意/剧本/分镜/宫格/视频/配音等 .md）。
- `uvicorn` 显式包含（agent 的 ASGI server 动态导入）。

## 编剧 Agent 在打包后如何启动
开发态用 `python -m screenwriter_agent` 拉子进程；打包后 `sys.executable` 是 `main.exe`（无 `-m`），
故同一 exe 兼作 agent 宿主：`lifecycle` 改用 `main.exe --run-agent screenwriter --port N`，
`main._maybe_run_agent` 在该进程内直接跑 agent server（见 `screenwriter_lifecycle._agent_command` /
`main._maybe_run_agent`，有单测守护）。

## 务必排除
- `license_admin/`（含私钥逻辑）已用 `--nofollow-import-to=license_admin` 排除。
- `license_admin/private_key.pem` 绝不进任何构建/仓库。
- `tests/`（测试代码）已用 `--nofollow-import-to=tests` 排除。
- **个人配置 `.env` / `settings.json`（含 api_key、项目路径）不打包**：它们是仓库根散文件，
  不在任何包内，Nuitka 不会收录；切勿用 `--include-data-file` 把它们加进来。运行时配置写到
  用户目录 `~/.drama_shot_master/`，与分发包隔离。

## 配乐重依赖（按需）
`sound_track_agent` 的 `demucs/librosa/torch` 为函数内 lazy import，默认**不**打进包（避免数 GB 体积）。
基础配乐链路（云端 RunningHub）不受影响；若要离线人声分离/卡点，自行在 bat 追加
`--include-package=librosa --include-package=demucs` 等并接受体积膨胀。

## 减少杀软误报（建议，非必须）
- 用代码签名证书签 `main.dist/*.exe`。
- 保持多文件模式（不要 --onefile）。

## 安全边界（务必知悉）
非对称签名杜绝 keygen/伪造、机器绑定防转发；但挡不住有人反汇编 patch 掉验签。
已做：原生编译 + 多处分散校验。目标是抬高门槛而非绝对不可破。
