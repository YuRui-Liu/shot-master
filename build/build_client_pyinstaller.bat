@echo off
REM Drama-Shot-Master Client - PyInstaller build (onedir)
REM Requires: pip install pyinstaller
REM
REM Output: build/dist_pyi/DramaShotMaster/  (distribute the whole folder)
REM Config: see build/drama_shot_master.spec (packages / templates / excludes)
REM
REM NOTE: PyInstaller bundles .pyc which CAN be unpacked/decompiled. If source
REM       protection matters, use the Nuitka build instead (build/build_client.bat).
REM
REM cd to repo root so top-level packages resolve.
cd /d %~dp0..
pyinstaller --noconfirm --clean ^
  --distpath build/dist_pyi ^
  --workpath build/work_pyi ^
  build/drama_shot_master.spec
echo Done. Output: build/dist_pyi/DramaShotMaster/
