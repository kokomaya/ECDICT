@echo off
chcp 65001 >nul

cd /d "%~dp0"

REM ── 读取版本号 ──────────────────────────────────────────
for /f "tokens=*" %%v in ('.venv\Scripts\python -c "from quickdict.config import VERSION; print(VERSION)"') do set VER=%%v

echo ============================================
echo   QuickDict 一键打包  v%VER%
echo ============================================
echo.

REM ── 前置检查 ────────────────────────────────────────────
if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到虚拟环境，请先运行 setup.bat
    pause
    exit /b 1
)

if not exist "data\ecdict.db" (
    echo [错误] 未找到 data\ecdict.db，请先运行 setup.bat 构建数据库
    pause
    exit /b 1
)

REM ── 安装 PyInstaller ────────────────────────────────────
echo [1/4] 检查 PyInstaller ...
.venv\Scripts\pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo        安装 PyInstaller ...
    .venv\Scripts\pip install pyinstaller -q
)
echo        OK

REM ── 执行打包 ────────────────────────────────────────────
echo [2/4] 打包 QuickDict.exe ...
.venv\Scripts\pyinstaller quickdict.spec --noconfirm >nul 2>&1
if errorlevel 1 (
    echo [错误] PyInstaller 打包失败
    .venv\Scripts\pyinstaller quickdict.spec --noconfirm
    pause
    exit /b 1
)
echo        OK

REM ── 准备发布目录 ────────────────────────────────────────
set RELEASE_DIR=release\v%VER%
set APP_DIR=%RELEASE_DIR%\QuickDict
set DB_PKG=%RELEASE_DIR%\QuickDict-data

echo [3/4] 整理发布目录 (v%VER%) ...

if exist "%RELEASE_DIR%" rmdir /s /q "%RELEASE_DIR%"
mkdir "%APP_DIR%"
mkdir "%DB_PKG%\data"

REM 复制程序（exe + _internal）
xcopy "dist\QuickDict\*" "%APP_DIR%\" /e /q /y >nul

REM DB 单独打包到另一个目录
copy "data\ecdict.db" "%DB_PKG%\data\ecdict.db" >nul

REM 生成使用说明
(
echo QuickDict v%VER% 使用说明
echo ========================
echo.
echo 【简介】
echo.
echo   QECDict（QuickDict）是一款基于 ECDICT 词典数据库的 Windows 屏幕取词
echo   翻译工具。支持 UI Automation 和 OCR 两种取词方式，适用于浏览器、编辑器、
echo   PDF 阅读器、图片等多种场景。无需联网，全部本地运行。
echo.
echo   词典数据来源: ECDICT — 自由英汉词典（340 万词条）
echo   项目主页: https://github.com/skywind3000/ECDICT
echo.
echo ============================================================
echo.
echo 【部署步骤】
echo.
echo   1. 解压 QuickDict.zip（程序包）到任意目录
echo   2. 解压 QuickDict-data.zip（数据库包）
echo   3. 将 QuickDict-data\data\ 文件夹复制到 QuickDict\ 下
echo.
echo   最终目录结构：
echo.
echo     QuickDict\
echo       QuickDict.exe        主程序
echo       使用说明.txt          本文件
echo       _internal\           运行时依赖（勿删除）
echo       data\
echo         ecdict.db           词典数据库（~800MB）
echo.
echo   4. 双击 QuickDict.exe 启动
echo.
echo ============================================================
echo.
echo 【快捷键】
echo.
echo   Ctrl × 2（连按两次）   激活 / 关闭取词模式
echo   Esc                    退出取词模式
echo.
echo ============================================================
echo.
echo 【触发方式】（右键托盘 → 触发方式）
echo.
echo   悬停取词（默认）        鼠标悬停在英文单词上自动弹出翻译
echo   Ctrl 键取词            取词模式下，单按一次 Ctrl 对当前
echo                          鼠标位置进行取词
echo.
echo   提示：悬停模式适合阅读场景；Ctrl 键模式适合需要精确控制
echo         取词时机的场景，避免鼠标滑过时误触发。
echo.
echo ============================================================
echo.
echo 【取词模式】（右键托盘 → 取词模式）
echo.
echo   自动（UIA→OCR）        先尝试 UI Automation 取词，失败后
echo                          自动回退到 OCR 截图识别（推荐）
echo   仅 UIA                 仅使用 UI Automation（适合浏览器、
echo                          编辑器等标准文本控件）
echo   仅 OCR                 仅使用 OCR 截图识别（适合图片、PDF、
echo                          游戏等非标准界面）
echo.
echo ============================================================
echo.
echo 【功能特性】
echo.
echo   - 翻译卡片弹窗         鼠标附近弹出美观的翻译卡片
echo   - 词形还原（Lemma）    自动识别 running → run 等变形
echo   - 模糊匹配             找不到精确词条时尝试近似匹配
echo   - 词根词缀             显示单词的词根词缀拆解（如有）
echo   - 系统托盘常驻         后台运行，不占用任务栏
echo   - 多显示器 DPI 感知    支持不同缩放比例的多显示器环境
echo.
echo ============================================================
echo.
echo 【系统要求】
echo.
echo   - Windows 10 / 11（64 位）
echo   - 无需安装 Python 或其他运行时
echo   - 磁盘空间：程序约 80MB + 数据库约 800MB
echo.
echo ============================================================
echo.
echo 【注意事项】
echo.
echo   1. 首次启动后程序运行在系统托盘（屏幕右下角），没有主窗口。
echo      如果看不到蓝色 D 图标，请点击托盘区的展开箭头。
echo.
echo   2. _internal 文件夹是程序运行所需的依赖，请勿删除或移动。
echo.
echo   3. 不同显示器的缩放比例不一致时，可能导致取词位置偏移。
echo      建议各显示器设置相同的缩放比例（如 100%% 或 150%%）。
echo.
echo   4. OCR 模式首次使用时加载模型可能稍有延迟（约 1-2 秒），
echo      后续调用会使用缓存，响应更快。
echo.
echo   5. 取词结果依赖 ECDICT 词典数据，部分专业术语或新词可能
echo      无法识别。
echo.
echo ============================================================
echo.
echo 【常见问题】
echo.
echo   Q: 启动后没有窗口？
echo   A: QuickDict 运行在系统托盘，查看屏幕右下角托盘区的蓝色 D 图标。
echo.
echo   Q: 主显示器取词失败，副屏正常？
echo   A: 请在系统设置中确认各显示器的缩放比例一致（推荐 100%% 或 150%%）。
echo.
echo   Q: 图片/PDF 上无法取词？
echo   A: 右键托盘 → 取词模式 → 切换为「仅 OCR」或「自动」。
echo.
echo   Q: Ctrl 键取词模式下，双击 Ctrl 同时也会取词？
echo   A: 双击 Ctrl 用于切换取词模式开关，这是正常行为，不影响使用。
echo.
echo   Q: 如何完全退出程序？
echo   A: 右键托盘图标 → 退出。
echo.
echo ============================================================
echo.
echo 【开源信息】
echo.
echo   QECDict 基于以下开源项目：
echo.
echo   - ECDICT 词典数据库    https://github.com/skywind3000/ECDICT
echo   - RapidOCR             https://github.com/RapidAI/RapidOCR
echo   - PyQt6                https://www.riverbankcomputing.com/software/pyqt/
echo   - pynput               https://github.com/moses-palmer/pynput
echo   - uiautomation         https://github.com/yinkaisheng/Python-UIAutomation-for-Windows
) > "%RELEASE_DIR%\使用说明.txt"

echo        OK

REM ── 输出结果 ────────────────────────────────────────────
echo [4/4] 打包完成！
echo.
echo   发布目录: %RELEASE_DIR%\
echo.
echo   %APP_DIR%\             ← 程序（分发给用户）
echo     QuickDict.exe
echo     _internal\
echo.
echo   %DB_PKG%\              ← 数据库（单独分发）
echo     data\ecdict.db
echo.
echo   使用方式:
echo     将 %DB_PKG%\data\ 复制到 %APP_DIR%\ 下
echo     双击 QuickDict.exe 即可运行
echo.
pause
