@echo off
chcp 65001 >nul
setlocal

REM Switch console to UTF-8 so paths and prints are not mangled by GBK.
REM All echo strings below are ASCII to avoid any encoding mismatch.

if not exist .env (
    echo [WARN] .env not found. Copying .env.example and opening Notepad...
    copy .env.example .env
    notepad .env
)

REM Check shot-master availability
python -c "import shot_master" 2>NUL
if errorlevel 1 (
    echo [INFO] Installing local shot-master...
    pip install -e ..\..\shot-master
    if errorlevel 1 goto :install_failed
)

REM Check this project's deps
python -c "import fastapi" 2>NUL
if errorlevel 1 (
    echo [INFO] Installing project dependencies...
    pip install -e .
    if errorlevel 1 goto :install_failed
)

echo [INFO] Starting uvicorn at http://127.0.0.1:7866 ...
python -m app.main
goto :eof

:install_failed
echo [ERROR] pip install failed. See messages above. Press any key to exit.
pause >nul
exit /b 1
