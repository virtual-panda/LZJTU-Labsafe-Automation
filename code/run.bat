@echo off
REM =====================================================================
REM  LabSecAutomation 启动器
REM ---------------------------------------------------------------------
REM  前提：已经运行过 install\scripts\install.bat 完成安装
REM  用法：直接双击本文件
REM
REM  本文件必须放在代码目录目录，与 demo.py、template.png 等同级。
REM  编码为 GBK + CRLF，不要另存为 UTF-8，否则 cmd 会解析出错。
REM =====================================================================

setlocal
chcp 936 >nul 2>&1

REM ---------------------------------------------------------------------
REM  关键：把工作目录切到本 bat 所在的目录，也就是代码目录。
REM
REM  为什么必须这么做？
REM    demo.py 用相对路径访问资源文件，例如 template.png、textCourses.json、
REM    videoCourseTarget.png 等。这些路径是相对当前工作目录解析的，
REM    而 Windows 双击 bat 时工作目录可能是 System32 或其它位置。
REM    不切目录的话程序会找不到图片和 json 文件。
REM ---------------------------------------------------------------------
cd /d "%~dp0"

set "VENV_PY=%~dp0.venv\Scripts\python.exe"
set "ENTRY=%~dp0demo.py"

echo.
echo =====================================================
echo   LabSecAutomation
echo =====================================================
echo.
echo   工作目录: %CD%
echo.

REM ---- 检查虚拟环境是否装好 ----
if not exist "%VENV_PY%" (
    echo [错误] 还没有安装，找不到虚拟环境:
    echo        %VENV_PY%
    echo.
    echo 请先双击运行 install\scripts\install.bat
    echo.
    pause
    exit /b 1
)

REM ---- 检查虚拟环境是否「真的能跑」----
REM 不能只看文件在不在：从别的机器或别的路径拷过来的 .venv，
REM 里面的 python.exe 还在，但它记录的 Python 路径已经失效，一跑就报错。
REM 所以这里实际运行一次做验证。
"%VENV_PY%" -c "import sys" >nul 2>&1
if errorlevel 1 (
    echo [错误] 虚拟环境无法运行:
    echo        %VENV_PY%
    echo.
    echo 这个 .venv 可能是从别的机器或别的路径拷贝过来的，需要重建。
    echo 请双击运行 install\scripts\install.bat 重新安装。
    echo.
    pause
    exit /b 1
)

REM ---- 检查主程序是否存在 ----
if not exist "%ENTRY%" (
    echo [错误] 找不到主程序:
    echo        %ENTRY%
    echo.
    echo 请确认 run.bat 放在代码目录目录，与 demo.py 在一起。
    echo.
    pause
    exit /b 1
)

REM ---- 检查程序运行需要的资源文件 ----
set "MISSING="
if not exist "template.png" set "MISSING=%MISSING% template.png"
if not exist "template-videoCourse.png" set "MISSING=%MISSING% template-videoCourse.png"
if not exist "videoCourseTarget.png" set "MISSING=%MISSING% videoCourseTarget.png"
if not exist "videoCourseFinished.png" set "MISSING=%MISSING% videoCourseFinished.png"
if not exist "textCourses.json" set "MISSING=%MISSING% textCourses.json"
if not exist "videoCourses.json" set "MISSING=%MISSING% videoCourses.json"

if not "%MISSING%"=="" (
    echo [警告] 以下资源文件缺失:
    echo   %MISSING%
    echo.
    echo 这些文件是程序运行必需的，请确认项目文件完整后再运行。
    echo.
    pause
    exit /b 1
)

echo [信息] 环境检查通过，正在启动程序...
echo.
echo   提示:
echo     - 程序运行期间请不要关闭本窗口
echo     - 需要紧急停止时，把鼠标快速甩到屏幕左上角
echo.
echo -----------------------------------------------------

REM ---------------------------------------------------------------------
REM  切换到 UTF-8 代码页。
REM  demo.py 内部执行了 sys.stdout.reconfigure，把中文日志按 UTF-8 输出。
REM  若这里保持 GBK，日志会变成乱码，所以运行 Python 期间必须用 65001。
REM ---------------------------------------------------------------------
chcp 65001 >nul 2>&1

"%VENV_PY%" "%ENTRY%"
set "RC=%ERRORLEVEL%"

REM 切回 GBK，让本脚本后面的中文提示正常显示
chcp 936 >nul 2>&1

echo -----------------------------------------------------
echo.
if "%RC%"=="0" (
    echo [完成] 程序已正常退出。
) else (
    echo [注意] 程序退出代码为 %RC%，可能中途出错了。
)
echo.

pause
endlocal
exit /b %RC%
