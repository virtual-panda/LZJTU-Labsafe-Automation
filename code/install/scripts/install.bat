@echo off
REM =====================================================================
REM  LabSecAutomation 离线一键安装 - 启动器
REM ---------------------------------------------------------------------
REM  为什么需要这个 bat？
REM    Windows 默认不允许双击运行 .ps1 文件（会被"记事本打开"或拒绝执行）。
REM    这个 bat 负责用正确的参数调用 PowerShell 脚本。
REM
REM  用法：直接双击本文件即可。
REM
REM  本文件编码为 GBK(936) + CRLF 换行，不要另存为 UTF-8，否则 cmd 会解析出错。
REM =====================================================================

setlocal
chcp 936 >nul 2>&1

REM 切换到脚本所在目录，保证相对路径正确
cd /d "%~dp0"

set "PS1=%~dp0install_offline.ps1"

echo.
echo =====================================================
echo   LabSecAutomation 离线一键安装
echo =====================================================
echo.

REM ---- 检查 PowerShell 脚本是否存在 ----
if not exist "%PS1%" (
    echo [错误] 找不到安装脚本:
    echo        %PS1%
    echo.
    echo 请确认 install\scripts\ 目录里有 install_offline.ps1 文件，
    echo 且不要单独拷贝这个 bat 文件。
    echo.
    pause
    exit /b 1
)

REM ---- 检查 install 目录结构是否完整 ----
if not exist "%~dp0..\python" (
    echo [错误] 找不到 ..\python 目录，离线安装包不完整。
    echo.
    echo 正确的目录结构应为：
    echo   install\
    echo     python\      依赖的 Python 安装程序
    echo     packages\    依赖包
    echo     scripts\     本脚本
    echo.
    echo 请确认整个 install 目录一起拷贝。
    echo.
    pause
    exit /b 1
)

if not exist "%~dp0..\packages" (
    echo [错误] 找不到 ..\packages 目录，离线安装包不完整。
    echo 请确认整个 install 目录一起拷贝。
    echo.
    pause
    exit /b 1
)

REM ---- 选择 PowerShell 可执行文件 ----
REM 优先用系统自带的 Windows PowerShell 5.1（兼容性最好）
set "PSEXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PSEXE%" (
    set "PSEXE=powershell.exe"
)

REM ---------------------------------------------------------------------
REM  自检：确认当前系统允许执行 PowerShell 脚本
REM ---------------------------------------------------------------------
REM  做法：临时写一个只含 exit 42 的探针脚本，用真实的调用方式执行它。
REM  只有当脚本"确实被跑起来"时才会返回 42；被策略拦截时会返回其它值。
REM
REM  为什么需要这步？
REM    个人电脑上，下面的 -ExecutionPolicy Bypass 足以绕过默认限制，
REM    不需要用户做任何设置（已实测：Restricted / RemoteSigned 下都能绕过）。
REM    但公司或学校统一管控的电脑可能用组策略或 AppLocker 彻底禁止脚本，
REM    那种情况下 Bypass 也无效。提前查出来才能给出明确提示，
REM    而不是让用户对着一堆报错发懵。
set "PROBE=%TEMP%\labsec_ps_probe_%RANDOM%.ps1"
set "PROBE_RC=42"
(echo exit 42)>"%PROBE%" 2>nul
if not exist "%PROBE%" goto :labsec_probe_done

"%PSEXE%" -NoProfile -ExecutionPolicy Bypass -File "%PROBE%" >nul 2>&1
set "PROBE_RC=%ERRORLEVEL%"
del "%PROBE%" >nul 2>&1

:labsec_probe_done
if not "%PROBE_RC%"=="42" (
    echo [错误] 当前系统禁止运行 PowerShell 脚本，安装无法继续。
    echo.
    echo 本安装脚本依赖 PowerShell 完成安装，但系统策略阻止了脚本执行。
    echo 这通常出现在公司或学校统一管控的电脑上。
    echo.
    echo 可以尝试：
    echo   1. 若是个人电脑，以管理员身份打开 PowerShell 后执行：
    echo        Set-ExecutionPolicy -Scope LocalMachine RemoteSigned
    echo   2. 若是公司/学校电脑，一般由 IT 的组策略锁定，本地无法自行解除，
    echo      请联系 IT 管理员
    echo   3. 或换一台没有此类限制的电脑运行安装
    echo.
    pause
    exit /b 1
)

echo [信息] 正在启动安装程序...
echo.

REM -NoProfile             不加载用户 profile，避免干扰
REM -ExecutionPolicy Bypass 绕过执行策略限制（仅本次进程，不修改系统设置）
REM -File                  执行指定的 ps1 脚本
"%PSEXE%" -NoProfile -ExecutionPolicy Bypass -File "%PS1%"

set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo [完成] 安装脚本执行结束。
) else (
    echo [注意] 安装脚本返回代码 %RC%，可能存在问题，请查看上方日志。
)
echo.

REM 脚本内部已 pause 过，这里再兜底一次，防止窗口一闪而过。
REM 被「启动程序.exe」调用时（LABSEC_NO_PAUSE=1）安装完还要接着启动程序，
REM 这种情况下不能停。
if not defined LABSEC_NO_PAUSE pause
endlocal
exit /b %RC%
