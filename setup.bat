@echo off
chcp 65001 >nul
echo ============================================
echo   QuickDict 一键初始化
echo ============================================
echo.

cd /d "%~dp0"

REM 1. 检查 Python 虚拟环境
if not exist ".venv\Scripts\python.exe" (
    echo [1/3] 创建虚拟环境 ...
    python -m venv .venv
) else (
    echo [1/3] 虚拟环境已存在，跳过
)

REM 2. 安装依赖
echo [2/3] 安装依赖 ...
.venv\Scripts\pip install -r quickdict\requirements.txt -q

REM 3. 构建数据库
echo [3/3] 构建词典数据库 ...
.venv\Scripts\python -m quickdict.build_db
if errorlevel 1 (
    echo.
    echo [错误] 数据库构建失败，请检查 CSV 文件是否存在
    pause
    exit /b 1
)

echo.
echo ============================================
echo   初始化完成！可执行以下命令启动：
echo   .venv\Scripts\python -m quickdict.main
echo ============================================
pause
