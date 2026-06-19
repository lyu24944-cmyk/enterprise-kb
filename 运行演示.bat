@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ========================================
echo  企业知识库 MVP - 一键启动
echo ========================================
echo.

if not exist "backend\.venv\Scripts\python.exe" (
    echo [1/5] 创建 Python 虚拟环境...
    python -m venv backend\.venv
)

echo [2/5] 安装后端依赖...
call backend\.venv\Scripts\activate.bat
pip install -r backend\requirements.txt -q

if not exist "backend\.env" (
    echo.
    echo 请先配置 DeepSeek API Key:
    copy backend\.env.example backend\.env
    notepad backend\.env
    echo 配置完成后请重新运行本脚本。
    pause
    exit /b 1
)

echo [3/5] 生成演示文档并入库...
python scripts\seed_demo_docs.py

if not exist "frontend\node_modules" (
    echo [4/5] 安装前端依赖...
    pushd frontend
    call npm install
    popd
) else (
    echo [4/5] 前端依赖已存在，跳过
)

echo [5/5] 启动服务...
start "Enterprise-KB-Backend" cmd /k "cd /d %~dp0backend && .venv\Scripts\activate.bat && uvicorn app.main:app --reload --port 8000"
timeout /t 3 /nobreak >nul
start "Enterprise-KB-Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo 后端: http://127.0.0.1:8000
echo 前端: http://localhost:5173
echo 文档: http://127.0.0.1:8000/docs
echo.
pause
