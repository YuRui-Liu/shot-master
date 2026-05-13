@echo off
setlocal

REM 检查 .env 是否存在
if not exist .env (
    echo [WARN] .env 不存在，先拷贝 .env.example 并填写 API Key
    copy .env.example .env
    notepad .env
)

REM 检查 shot-master 是否已装
python -c "import shot_master" 2>NUL
if errorlevel 1 (
    echo [INFO] 安装本地 shot-master...
    pip install -e ..\shot-master
)

REM 检查本项目依赖
python -c "import fastapi" 2>NUL
if errorlevel 1 (
    echo [INFO] 安装本项目依赖...
    pip install -e .
)

REM 启动
python -m app.main

endlocal
