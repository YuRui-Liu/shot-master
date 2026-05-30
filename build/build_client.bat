@echo off
REM Drama-Shot-Master 客户端 Nuitka 打包（原生编译，不泄露源码）
REM 前置: pip install nuitka ；建议装 MSVC 或 clang
REM
REM 打包内容：
REM   - drama_shot_master   GUI 主程序
REM   - screenwriter_agent  编剧 Agent（FastAPI；打包后由同一 exe 用
REM                          `--run-agent screenwriter` 在子进程内启动）
REM   - sound_track_agent   配乐/音效（重依赖 demucs/librosa 为函数内 lazy import，
REM                          默认不打进包；如需离线分离/卡点，自行加 --include-package=librosa 等）
REM   - uvicorn             agent 的 ASGI server（动态导入，显式包含）
REM   - 提示词模板 + 资源（见下方 --include-data-dir）
REM 不打包（避免泄露 / 体积）：
REM   - license_admin       授权管理（含私钥逻辑）→ --nofollow-import-to
REM   - tests               测试代码          → --nofollow-import-to
REM   - 个人配置 .env / settings.json（含 api_key、项目路径）：均为仓库根散文件，
REM     不在任何包内，Nuitka 不会收录；切勿用 --include-data-file 把它们加进来。
python -m nuitka ^
  --standalone ^
  --enable-plugin=pyside6 ^
  --include-package=drama_shot_master ^
  --include-package=screenwriter_agent ^
  --include-package=sound_track_agent ^
  --include-package=uvicorn ^
  --nofollow-import-to=license_admin ^
  --nofollow-import-to=tests ^
  --include-data-dir=drama_shot_master/templates=drama_shot_master/templates ^
  --include-data-dir=drama_shot_master/assets=drama_shot_master/assets ^
  --include-data-dir=screenwriter_agent/templates=screenwriter_agent/templates ^
  --windows-icon-from-ico=drama_shot_master/assets/app_icon.ico ^
  --windows-console-mode=disable ^
  --output-dir=build/dist ^
  drama_shot_master/main.py
echo 完成。产物在 build/dist/main.dist/
