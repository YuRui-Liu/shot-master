@echo off
chcp 65001 >nul
setlocal

if not exist .env (
    echo [WARN] .env not found. Copying .env.example and opening Notepad...
    copy .env.example .env
    notepad .env
)

python -c "import shot_master" 2>NUL
if errorlevel 1 (
    echo [INFO] Installing local shot-master...
    pip install -e ..\..\shot-master
    if errorlevel 1 goto :install_failed
)

python -c "from PySide6.QtWidgets import QApplication" 2>NUL
if errorlevel 1 (
    echo [INFO] Installing project dependencies...
    pip install -e .
    if errorlevel 1 goto :install_failed
)

python -m app.main
goto :eof

:install_failed
echo [ERROR] pip install failed. See messages above. Press any key to exit.
pause >nul
exit /b 1
