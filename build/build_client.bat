@echo off
REM Drama-Shot-Master 客户端 Nuitka 打包（原生编译，不泄露源码）
REM 前置: pip install nuitka ；建议装 MSVC 或 clang
python -m nuitka ^
  --standalone ^
  --enable-plugin=pyside6 ^
  --include-package=drama_shot_master ^
  --nofollow-import-to=license_admin ^
  --nofollow-import-to=tests ^
  --include-data-dir=drama_shot_master/templates=drama_shot_master/templates ^
  --include-data-dir=drama_shot_master/assets=drama_shot_master/assets ^
  --windows-icon-from-ico=drama_shot_master/assets/app_icon.ico ^
  --windows-console-mode=disable ^
  --output-dir=build/dist ^
  drama_shot_master/main.py
echo 完成。产物在 build/dist/main.dist/
