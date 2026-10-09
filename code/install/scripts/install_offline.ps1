<#
=====================================================================
 LabSecAutomation 一键离线安装脚本
---------------------------------------------------------------------
 作用：
   1. 从本地 install/python/ 安装 Python 3.14.7（无需联网）
   2. 在代码目录创建虚拟环境 .venv
   3. 把全部第三方依赖装进 .venv（纯 wheel，无需联网、无需编译）
   4. 全程不访问互联网，适合无网 / 内网 / pip 访问缓慢的机器

 自检（重要）：
   每次运行都会先自检已有的 .venv 到底对不对，三层检查：
     ① 能不能跑  —— 实际启动一次 python.exe（拷来的 venv 会在这里露馅）
     ② 版本对不对 —— 必须是 Python 3.14，否则装不上 cp314 的 wheel
     ③ 依赖齐不齐 —— 缺什么才装什么；全都齐全时直接跳过 pip，几秒结束
   只有确实有问题才会清理重建 / 重装。
   全部通过后会在 .venv 里写入就绪标记 .labsec_ready，
   供「启动程序.exe」判断环境能否直接使用。

 装完之后：
   双击分发包根目录的「启动程序.exe」即可启动程序。

 用法（推荐）：
   双击 install/scripts/install.bat
 或手动：
   powershell -ExecutionPolicy Bypass -File install_offline.ps1

 参数：
   -InstallDir <路径>   自定义 Python 安装目录
                        （默认 %LOCALAPPDATA%\Programs\Python\Python314）
   -VenvDir <路径>      自定义虚拟环境目录（默认 <代码目录>\.venv）
   -SkipPython          跳过 Python 安装，直接用系统已有的 Python 3.14
=====================================================================
#>

[CmdletBinding()]
param(
    [string]$InstallDir = "",
    [string]$VenvDir    = "",
    [switch]$SkipPython
)

# ---------------------------------------------------------------
# 全局设置
# ---------------------------------------------------------------
$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"   # 关掉进度条，避免拖慢 IO

# 输出编码：不强制 UTF-8，跟随调用方控制台的代码页。
# 本脚本通常由 install.bat 以 chcp 936 调用；若这里强制 UTF-8，中文会变成乱码。
# 脚本文件本身保存为 UTF-8 with BOM，PowerShell 5.1 能正确读取其中的中文。

# ---------------------------------------------------------------
# 路径解析
#   分发包结构：
#     分发包根\                          ← 放「启动程序.exe」
#       └── code\                        ← 本脚本所说的「代码目录」
#             ├── run.bat  demo.py  资源文件
#             ├── .venv\                 （本脚本创建）
#             └── install\
#                   ├── python\  packages\
#                   └── scripts\         ← 本脚本在这里
#
#   所以从本脚本往上：
#     向上一级 -> install\    （离线包目录）
#     再向上一级 -> code\      （.venv 和资源文件所在，即下面的 $CodeDir）
#   用 $PSScriptRoot 保证无论从哪个目录调用都能定位正确。
# ---------------------------------------------------------------
$ScriptDir   = $PSScriptRoot
$InstallRoot = Split-Path -Parent $ScriptDir          # install/
$CodeDir    = Split-Path -Parent $InstallRoot        # code 目录（.venv 与资源文件所在）

$PythonExeName   = "python-3.14.7-amd64.exe"
$PythonInstaller = Join-Path $InstallRoot "python\$PythonExeName"
$PackagesDir     = Join-Path $InstallRoot "packages"
$GetPipScript    = Join-Path $ScriptDir  "get-pip.py"
$ReqFile         = Join-Path $InstallRoot "requirements-offline.txt"

# 目标 Python 版本：本离线包内的 wheel 都是 cp314 的，必须匹配
$TargetPythonMajorMinor = "3.14"

# 默认 Python 安装目录：用户目录，免管理员
if ([string]::IsNullOrWhiteSpace($InstallDir)) {
    $InstallDir = Join-Path $env:LOCALAPPDATA "Programs\Python\Python314"
}

# 默认 venv 目录：代码目录下的 .venv
if ([string]::IsNullOrWhiteSpace($VenvDir)) {
    $VenvDir = Join-Path $CodeDir ".venv"
}

# ---------------------------------------------------------------
# 就绪标记
# ---------------------------------------------------------------
# 全部自检通过后写入，供「启动程序.exe」快速判断环境能不能直接用。
# 有意放在 .venv 内部：一旦 .venv 被删除或重建，标记自然失效，
# 不会出现「标记还在、环境其实已经没了」的假阳性。
$ReadyStamp    = Join-Path $VenvDir ".labsec_ready"
$ReadyStampVer = 1

# ---------------------------------------------------------------
# 自检清单（单一来源，下面所有检查都引用它，避免两处清单不一致）
# ---------------------------------------------------------------
# 运行所需的关键模块
# 注意：pyclipper / onnxruntime 也列进来 —— 它们依赖 VC++ 运行库，
# 在精简系统上最典型的失败就是这两个导入失败，必须让安装自检能抓到。
$RequiredModules = @(
    "cv2", "numpy", "pyautogui", "PIL", "mss", "rapidocr",
    "pyclipper", "onnxruntime",
    "win32gui", "inputimeout"
)

# 自带 VC++ 运行库要部署的 DLL（源在 install\vcruntime\，部署进 venv 的 _vcruntime\）
# msvcp140 / msvcp140_1 是 pyclipper 和 onnxruntime 必需；
# vcruntime140 / vcruntime140_1 是保险（理论上有 Python 就一定有，但带上无妨）。
$RequiredVcruntime = @(
    "msvcp140.dll",
    "msvcp140_1.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll"
)

# 项目运行所需的资源文件（demo.py 按「当前工作目录」查找它们）
$RequiredResources = @(
    "template.png",
    "template-videoCourse.png",
    "videoCourseTarget.png",
    "videoCourseFinished.png",
    "textCourses.json",
    "videoCourses.json"
)

# ---------------------------------------------------------------
# 输出辅助函数（统一前缀 + 颜色）
# ---------------------------------------------------------------
function Write-Step  { param([string]$m) Write-Host ""; Write-Host "==== $m ====" -ForegroundColor Cyan }
function Write-Ok    { param([string]$m) Write-Host "  [OK]   $m" -ForegroundColor Green }
function Write-Info  { param([string]$m) Write-Host "  [..]   $m" -ForegroundColor Gray }
function Write-Warn  { param([string]$m) Write-Host "  [警告] $m" -ForegroundColor Yellow }
function Write-Err   { param([string]$m) Write-Host "  [错误] $m" -ForegroundColor Red }

function Stop-WithError {
    param([string]$Message)
    Write-Host ""
    Write-Err $Message
    Write-Host ""
    Write-Host "安装已中止。" -ForegroundColor Red
    if (-not $env:LABSEC_NO_PAUSE) {
        Write-Host "按任意键关闭..." -ForegroundColor Gray
        try { $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown") } catch { }
    }
    exit 1
}

# ---------------------------------------------------------------
# 辅助：查找系统里已注册的 Python 3.14
# ---------------------------------------------------------------
# Python 安装器有个重要机制：同一版本只允许注册一次。
# 如果注册表里已有 3.14 的安装记录，再次静默安装会「立即返回退出码 0
# 但什么都不做」——即静默跳过。这里主动检测这种情况，避免用户困惑。
function Find-RegisteredPython314 {
    $keys = @(
        "HKCU:\SOFTWARE\Python\PythonCore\3.14\InstallPath",
        "HKLM:\SOFTWARE\Python\PythonCore\3.14\InstallPath",
        "HKCU:\SOFTWARE\WOW6432Node\Python\PythonCore\3.14\InstallPath",
        "HKLM:\SOFTWARE\WOW6432Node\Python\PythonCore\3.14\InstallPath"
    )
    foreach ($k in $keys) {
        try {
            if (Test-Path $k) {
                $val = (Get-ItemProperty -Path $k -ErrorAction Stop).'(default)'
                if ($val) {
                    $exe = Join-Path $val.TrimEnd('\') "python.exe"
                    if (Test-Path $exe) { return $exe }
                }
            }
        } catch { }
    }
    return $null
}

# 检查某个 python.exe 是不是 3.14
function Test-IsPython314 {
    param([string]$Exe)
    try {
        $out = & $Exe -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>&1
        return ($out.Trim() -eq $TargetPythonMajorMinor)
    } catch {
        return $false
    }
}

# ---------------------------------------------------------------
# 横幅
# ---------------------------------------------------------------
Write-Host ""
Write-Host "=====================================================" -ForegroundColor White
Write-Host "  LabSecAutomation  离线一键安装" -ForegroundColor White
Write-Host "  Python 3.14.7 + 虚拟环境 .venv（全程无需联网）" -ForegroundColor White
Write-Host "=====================================================" -ForegroundColor White
Write-Host ""
Write-Info "install 目录 : $InstallRoot"
Write-Info "代码目录     : $CodeDir"
Write-Info "虚拟环境位置 : $VenvDir"
Write-Host ""

# ---------------------------------------------------------------
# 0. 前置检查：离线包是否齐全
# ---------------------------------------------------------------
Write-Step "0/6 检查离线安装包完整性"

$requiredPaths = @(
    @{ Path = $PythonInstaller; Name = "Python 安装程序" },
    @{ Path = $PackagesDir;     Name = "依赖包目录"     },
    @{ Path = $ReqFile;         Name = "依赖清单"       }
)

$missingCritical = $false
foreach ($item in $requiredPaths) {
    if (Test-Path $item.Path) {
        Write-Ok "$($item.Name) 存在"
    } else {
        Write-Err "$($item.Name) 缺失: $($item.Path)"
        $missingCritical = $true
    }
}

if ($missingCritical) {
    Stop-WithError "关键的离线安装文件缺失，请确认 install/ 目录已完整拷贝（不要只拷贝 scripts/ 子目录）。"
}

$pkgFiles = @(Get-ChildItem -Path $PackagesDir -File -ErrorAction SilentlyContinue)
if ($pkgFiles.Count -eq 0) {
    Stop-WithError "依赖包目录是空的: $PackagesDir"
}
$wheelCount = @($pkgFiles | Where-Object { $_.Extension -eq ".whl" }).Count
Write-Ok "依赖包: $($pkgFiles.Count) 个文件（其中 wheel $wheelCount 个）"

if (-not (Test-Path $GetPipScript)) {
    Write-Warn "未找到 get-pip.py（仅在 pip 异常时才会用到，可忽略）"
}

# ---------------------------------------------------------------
# 1. 准备 Python 3.14
# ---------------------------------------------------------------
Write-Step "1/6 准备 Python $TargetPythonMajorMinor"

$pythonExe = Join-Path $InstallDir "python.exe"
$needInstall = $true

# 1a. 目标目录里已经有？
if (Test-Path $pythonExe) {
    Write-Ok "目标目录已有 Python: $pythonExe"
    $needInstall = $false
}

# 1b. 系统里已注册过 3.14？（安装器无法重复注册同版本）
if ($needInstall) {
    $registered = Find-RegisteredPython314
    if ($registered) {
        Write-Info "检测到系统中已注册 Python ${TargetPythonMajorMinor}:"
        Write-Info "  $registered"
        Write-Info "同版本无法重复安装，直接复用这个解释器。"
        $pythonExe = $registered
        $needInstall = $false
    }
}

# 1c. -SkipPython 时，从 PATH 里找
if ($needInstall -and $SkipPython) {
    Write-Info "已指定 -SkipPython，从 PATH 中查找 Python"
    $candidates = @(Get-Command python -All -ErrorAction SilentlyContinue |
                    Where-Object { $_.Source -notlike "*WindowsApps*" })
    $picked = $null
    foreach ($c in $candidates) {
        if (Test-IsPython314 $c.Source) { $picked = $c.Source; break }
    }
    if ($picked) {
        $pythonExe = $picked
        $needInstall = $false
        Write-Ok "使用 PATH 中的 Python: $pythonExe"
    } else {
        Stop-WithError "指定了 -SkipPython，但系统里找不到 Python $TargetPythonMajorMinor。"
    }
}

# 1d. 确实需要安装
if ($needInstall) {
    Write-Info "开始静默安装 Python（约 1 分钟，请耐心等待）..."

    # 关键参数：
    #   /quiet                    静默，无界面
    #   InstallAllUsers=0         仅当前用户，不需要管理员权限
    #   PrependPath=1             加入 PATH
    #   Include_pip=1             安装 pip
    #   Include_test=0            不装测试套件
    #   AssociateFiles=0          不改文件关联
    #   TargetDir                 安装目录
    $installArgs = @(
        "/quiet",
        "InstallAllUsers=0",
        "PrependPath=1",
        "Include_pip=1",
        "Include_test=0",
        "AssociateFiles=0",
        "Include_launcher=1",
        "TargetDir=`"$InstallDir`""
    )

    $proc = Start-Process -FilePath $PythonInstaller -ArgumentList $installArgs -Wait -PassThru

    if ($proc.ExitCode -ne 0) {
        Write-Warn "安装程序返回退出码 $($proc.ExitCode)（1603 通常表示目录被占用或权限问题）"
    }

    # 不能只信退出码，必须实际验证 python.exe 是否落地
    if (-not (Test-Path $pythonExe)) {
        $registered = Find-RegisteredPython314
        if ($registered) {
            Write-Warn "目标位置没有 python.exe，但系统里已注册 Python ${TargetPythonMajorMinor}:"
            Write-Warn "  $registered"
            Write-Info "改用这个已注册的解释器继续。"
            $pythonExe = $registered
        } else {
            Stop-WithError @"
Python 安装未成功：目标位置没有找到 python.exe
  预期路径: $pythonExe
  安装器退出码: $($proc.ExitCode)

可能的原因：
  1. 杀毒软件/安全软件拦截了静默安装 —— 请暂时关闭后重试
  2. 目标路径所在磁盘空间不足或无写入权限
  3. 系统里已有其它 Python $TargetPythonMajorMinor 注册记录（安装器会静默跳过）

排查建议：
  - 手动运行安装程序，看是否有可见错误：
      install\python\$PythonExeName
  - 或用 -InstallDir 指定另一个目录后重试
"@
        }
    } else {
        Write-Ok "Python 安装完成"
    }
}

# 1e. 最终校验版本
try {
    $verFull = & $pythonExe --version 2>&1
} catch {
    Stop-WithError "找到了 python.exe 但无法运行: $pythonExe`n$($_.Exception.Message)"
}

if (-not (Test-IsPython314 $pythonExe)) {
    $actual = & $pythonExe -c "import sys; print('%d.%d.%d' % sys.version_info[:3])" 2>&1
    Stop-WithError @"
Python 版本不匹配。
  需要: $TargetPythonMajorMinor.x
  实际: $actual  ($pythonExe)

本离线包内的依赖都是 cp314 的 wheel，只能用 Python $TargetPythonMajorMinor 安装。
请删除 .venv 后重跑安装脚本，或改用其它解释器。
"@
}
Write-Ok "Python 版本: $verFull"
Write-Info "解释器路径: $pythonExe"

# ---------------------------------------------------------------
# 辅助：虚拟环境自检
# ---------------------------------------------------------------

# ① 能不能跑？
#    只检查 python.exe 是否存在是不够的。
#    venv 内部会记录创建时所用 Python 的绝对路径（写在 pyvenv.cfg 的 home 项里），
#    如果把项目连同 .venv 一起拷到别的机器、或拷到另一个用户目录下，
#    python.exe 文件还在，但它会去那个已经不存在的路径找解释器，直接失败。
#    所以必须实际运行一次进程才能确认可用。
function Test-VenvUsable {
    param([string]$VenvPythonExe)
    if (-not (Test-Path $VenvPythonExe)) { return $false }
    try {
        $null = & $VenvPythonExe -c "import sys" 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

# ② Python 版本对不对？
#    venv 可能是用别的版本（比如 3.12）建的。那样即使能跑也没用 ——
#    本离线包里的依赖全是 cp314 的 wheel，装不上。
#    返回形如 "3.14"，取不到时返回空串。
function Get-VenvPythonVersion {
    param([string]$VenvPythonExe)
    try {
        $out = & $VenvPythonExe -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>&1
        if (-not $out) { return "" }
        return ($out | Select-Object -First 1).ToString().Trim()
    } catch {
        return ""
    }
}

# ---------------------------------------------------------------
# 2. 准备虚拟环境（自检：能不能跑 + 版本对不对）
# ---------------------------------------------------------------
Write-Step "2/6 检查虚拟环境"

$venvPython = Join-Path $VenvDir "Scripts\python.exe"
$needCreate = $true

if (-not (Test-Path $venvPython)) {
    Write-Info "虚拟环境尚未创建"
}
elseif (-not (Test-VenvUsable $venvPython)) {
    Write-Warn "虚拟环境存在，但无法运行，将自动重建"
    Write-Info "  常见原因：这个 .venv 是从别的机器或别的路径拷贝过来的，"
    Write-Info "  它内部记录的 Python 位置在当前环境下不存在。"
}
else {
    $venvVer = Get-VenvPythonVersion $venvPython
    if ($venvVer -ne $TargetPythonMajorMinor) {
        Write-Warn "虚拟环境里的 Python 是 $venvVer，不是本离线包要求的 $TargetPythonMajorMinor，将自动重建"
        Write-Info "  包内依赖全部是 cp$($TargetPythonMajorMinor.Replace('.','')) 的 wheel，版本必须一致。"
    }
    else {
        Write-Ok "虚拟环境可用（Python $venvVer），直接复用: $VenvDir"
        $needCreate = $false
    }
}

if ($needCreate) {
    # 清掉不可用/残缺的旧目录
    if (Test-Path $VenvDir) {
        Write-Info "清理旧的虚拟环境目录: $VenvDir"
        Remove-Item $VenvDir -Recurse -Force -ErrorAction SilentlyContinue
        if (Test-Path $VenvDir) {
            Stop-WithError @"
无法清理旧的虚拟环境目录（可能正被占用）: $VenvDir

请关闭正在使用它的程序（命令行窗口、编辑器、调试器等）后重试，
或手动删除该目录后再运行本脚本。
"@
        }
    }

    Write-Info "创建虚拟环境: $VenvDir"
    & $pythonExe -m venv $VenvDir

    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) {
        Stop-WithError "虚拟环境创建失败: $VenvDir`n请确认项目目录有写入权限，且磁盘空间充足。"
    }

    # 创建完也再验证一次，确保真的可用
    if (-not (Test-VenvUsable $venvPython)) {
        Stop-WithError @"
虚拟环境创建后仍然无法运行: $venvPython

请检查：
  1. 杀毒软件是否拦截了进程创建
  2. Python 安装是否完整（可手动运行查看报错）：
       $pythonExe
"@
    }

    $vver = & $venvPython --version 2>&1
    Write-Ok "虚拟环境已创建: $vver"
}

# ---------------------------------------------------------------
# 辅助：venv 自检（依赖模块 + 项目资源文件）
# ---------------------------------------------------------------
# 把检查逻辑集中在这儿，第 3 步（决定要不要装依赖）和第 5 步（最终验证）
# 复用同一份，避免两处清单不一致。
# 检查用的 Python 代码由 $RequiredModules / $RequiredResources 动态生成，
# 清单只维护一份。
function Invoke-VenvSelfCheck {
    param([string]$VenvPythonExe)

    $moduleListPy   = ($RequiredModules   | ForEach-Object { "'$_'" }) -join ", "
    $resourceListPy = ($RequiredResources | ForEach-Object { "'$_'" }) -join ", "

    $checkScript = @'
import os
import sys

# 1) 关键模块能否导入
mods = [@MODULES@]
ok, fail = [], []
for m in mods:
    try:
        __import__(m)
        ok.append(m)
    except Exception as e:
        fail.append("%s(%s)" % (m, type(e).__name__))

print("MODULES_OK:" + ",".join(ok))
if fail:
    print("MODULES_FAIL:" + ",".join(fail))

# 2) 项目资源文件（demo.py 按当前工作目录查找，所以必须在代码目录下检查）
resources = [@RESOURCES@]
missing = [r for r in resources if not os.path.isfile(r)]
if missing:
    print("RESOURCES_MISSING:" + ",".join(missing))
else:
    print("RESOURCES_OK")

sys.exit(1 if (fail or missing) else 0)
'@

    $checkScript = $checkScript.Replace("@MODULES@", $moduleListPy).Replace("@RESOURCES@", $resourceListPy)

    $tmpPy = Join-Path $env:TEMP "labsec_verify_$PID.py"
    Set-Content -Path $tmpPy -Value $checkScript -Encoding UTF8

    # 注意：Push-Location 到代码目录，模拟 run.bat 的运行环境
    Push-Location $CodeDir
    $output = & $VenvPythonExe $tmpPy 2>&1
    $code = $LASTEXITCODE
    Pop-Location
    Remove-Item $tmpPy -Force -ErrorAction SilentlyContinue

    $modsFail   = @()
    $resMissing = @()
    foreach ($line in $output) {
        if ($line -like "MODULES_FAIL:*") {
            $modsFail = @(($line.Substring(13) -split ",") | Where-Object { $_ })
        }
        elseif ($line -like "RESOURCES_MISSING:*") {
            $resMissing = @(($line.Substring(18) -split ",") | Where-Object { $_ })
        }
    }

    return [pscustomobject]@{
        Output           = $output
        ExitCode         = $code
        ModulesFail      = $modsFail
        ResourcesMissing = $resMissing
    }
}

# ---------------------------------------------------------------
# 3. 准备依赖（自检：缺什么装什么，齐全就跳过）
# ---------------------------------------------------------------
Write-Step "3/6 检查依赖"

Write-Info "正在自检依赖是否齐全..."
$check = Invoke-VenvSelfCheck $venvPython

$needPip = $true
if ($check.ModulesFail.Count -eq 0) {
    Write-Ok "依赖已齐全，跳过安装"
    $needPip = $false
} else {
    Write-Warn "以下模块缺失或异常，需要安装: $($check.ModulesFail -join ', ')"
}

if ($needPip) {
    # 说明：
    #   本离线包内所有依赖都已提供 wheel（包括 PyAutoGUI 等原本只有源码包的），
    #   因此安装时不需要联网、不需要 setuptools、不需要 C++ 编译器。
    #   pip 会自动优先选择 wheel。
    Write-Info "安装中，请稍候..."

    & $venvPython -m pip install `
        --no-index `
        --find-links "$PackagesDir" `
        --no-cache-dir `
        --no-warn-script-location `
        -r "$ReqFile"

    if ($LASTEXITCODE -ne 0) {
        Stop-WithError @"
依赖安装失败。

可能的原因：
  1. install/packages/ 目录内容不完整 —— 请确认整个目录都拷贝过来了
  2. 该 Python 版本与 wheel 不匹配 —— 需要 Python $TargetPythonMajorMinor

可以把上面 pip 的错误信息发给开发者。
"@
    }
    Write-Ok "依赖安装完成"
}

# ---------------------------------------------------------------
# 4. 部署自带 VC++ 运行库（.pth + add_dll_directory 机制）
# ---------------------------------------------------------------
# 背景：pyclipper / onnxruntime 的 C 扩展依赖 VC++ 2015-2022 运行库
#      （msvcp140.dll 等）。精简版系统（tiny10 等）没有这套运行库，
#      程序会报「DLL load failed while importing _pyclipper」。
# 做法（与 numpy / shapely 的 delvewheel 同款）：
#      把 4 个运行库 DLL 放进 venv 的 _vcruntime\ 目录，并生成一个
#      .pth + 补丁模块，Python 启动时自动把该目录加入 DLL 搜索路径。
#      免管理员；自带副本优先于系统目录，保证所有机器跑同一份。
Write-Step "4/6 部署自带 VC++ 运行库"

$VcruntimeSource = Join-Path $InstallRoot "vcruntime"

if (-not (Test-Path $VcruntimeSource)) {
    Write-Info "离线包里没有 vcruntime 目录（旧版安装包没有带），跳过本步骤。"
} else {
    # 用解释器自己报告 site-packages 位置 —— 不猜路径，用户名/布局怎么变都对
    $sitePackages = ""
    try {
        $sitePackages = (& $venvPython -c "import sysconfig; print(sysconfig.get_paths()['purelib'])").ToString().Trim()
    } catch { }

    if (-not $sitePackages -or -not (Test-Path $sitePackages)) {
        Write-Warn "找不到 venv 的 site-packages，自带运行库未能部署。"
        Write-Warn "若之后 pyclipper / onnxruntime 导入失败，请重跑一次安装。"
    } else {
        $VcruntimeDest = Join-Path $sitePackages "_vcruntime"
        New-Item -ItemType Directory -Force -Path $VcruntimeDest | Out-Null

        foreach ($dll in $RequiredVcruntime) {
            Copy-Item -Path (Join-Path $VcruntimeSource $dll) `
                      -Destination (Join-Path $VcruntimeDest $dll) -Force
        }
        Write-Ok "已复制 $($RequiredVcruntime.Count) 个运行库 DLL 到: $VcruntimeDest"

        # .pth 只负责「启动时 import 补丁模块」；路径由模块用 __file__ 自己推导，
        # 不写死任何绝对路径 —— 项目搬到任何目录（含中文/空格路径）都能用。
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)

        $pthContent = "import _labsec_vcrt"
        [System.IO.File]::WriteAllText((Join-Path $sitePackages "_labsec_vcrt.pth"), $pthContent + "`r`n", $utf8NoBom)

        $modContent = @'
"""LabSecAutomation 自带 VC++ 运行库加载补丁（安装程序自动生成，勿删）。

原理：Python 启动时处理 .pth 会 import 本模块；本模块把同目录下的
_vcruntime\\ 加入 DLL 搜索路径（os.add_dll_directory），这样 pyclipper /
onnxruntime 等 C 扩展就能用项目自带的 msvcp140.dll 等，
不再依赖系统里是否装了 VC++ 运行库（精简版 Windows 上没有）。
与 numpy / shapely 的 delvewheel 机制同款。
"""
import os as _os

_d = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "_vcruntime")
if _os.path.isdir(_d):
    # 句柄留在模块全局变量里，进程生命周期内目录一直有效
    _labsec_vcrt_handle = _os.add_dll_directory(_d)
'@
        [System.IO.File]::WriteAllText((Join-Path $sitePackages "_labsec_vcrt.py"), $modContent, $utf8NoBom)

        Write-Ok "已生成加载补丁: _labsec_vcrt.pth + _labsec_vcrt.py"
        Write-Info "之后 Python 每次启动都会自动加载自带运行库目录。"
    }
}

# ---------------------------------------------------------------
# 5. 验证
# ---------------------------------------------------------------
Write-Step "5/6 验证安装结果"

# 装过依赖就重新自检一次；走了快速路径（本来就不缺）则直接复用第 3 步的结果
if ($needPip) {
    $check = Invoke-VenvSelfCheck $venvPython
}

foreach ($line in $check.Output) {
    # 先转成字符串：Output 里可能混有 ErrorRecord（某个模块 import 时会往 stderr
    # 写警告，2>&1 重定向后是 ErrorRecord 对象，直接调 .Trim() 会炸）
    $text = "$line"
    if ($text -like "MODULES_OK:*") {
        Write-Ok "模块导入正常: $($text.Substring(11))"
    } elseif ($text -like "MODULES_FAIL:*") {
        Write-Err "模块导入失败: $($text.Substring(13))"
    } elseif ($text -like "RESOURCES_MISSING:*") {
        Write-Err "项目资源文件缺失: $($text.Substring(18))"
    } elseif ($text -like "RESOURCES_OK") {
        Write-Ok "项目资源文件齐全"
    } elseif ($text.Trim()) {
        Write-Info $text
    }
}

if ($check.ResourcesMissing.Count -gt 0) {
    Write-Host ""
    Write-Warn "缺少项目资源文件，程序运行时可能找不到它们。"
    Write-Warn "请确认代码目录（$CodeDir）里的图片和 json 文件齐全。"
}

# ---------------------------------------------------------------
# 6. 写入就绪标记
# ---------------------------------------------------------------
Write-Step "6/6 写入就绪标记"

$venvVerFull = ""
try {
    $venvVerFull = (& $venvPython --version 2>&1 | Select-Object -First 1).ToString().Trim()
} catch { }

if ($check.ModulesFail.Count -eq 0) {
    try {
        $stampText = @"
LabSecAutomation 虚拟环境就绪标记
stamp_version = $ReadyStampVer
created       = $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
python        = $venvVerFull
venv          = $VenvDir

说明：本文件由 install_offline.ps1 自动生成，用于让「启动程序.exe」判断
      运行环境是否已经装好、可以直接启动。删掉它无副作用，
      只是下次启动会重新自检一遍。
"@
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($ReadyStamp, $stampText, $utf8NoBom)
        Write-Ok "已写入: $ReadyStamp"
    } catch {
        Write-Warn "写入就绪标记失败（不影响本次安装，只是下次启动会再自检一遍）:"
        Write-Warn "  $($_.Exception.Message)"
    }
} else {
    Write-Warn "依赖自检未通过，不写就绪标记 —— 下次启动会重新引导安装。"
}

# ---------------------------------------------------------------
# 完成
# ---------------------------------------------------------------
Write-Host ""
Write-Host "=====================================================" -ForegroundColor Green
Write-Host "  安装完成！" -ForegroundColor Green
Write-Host "=====================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  虚拟环境 : $VenvDir" -ForegroundColor White
Write-Host "  Python   : $pythonExe" -ForegroundColor White
Write-Host ""
Write-Host "  下一步：双击分发包根目录的「启动程序.exe」启动程序" -ForegroundColor Yellow
Write-Host ""

if (-not $env:LABSEC_NO_PAUSE) {
    Write-Host "按任意键关闭..." -ForegroundColor Gray
    try { $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown") } catch { }
}

exit 0
