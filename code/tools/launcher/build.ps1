<# =====================================================================
 build.ps1 -- 编译 LabSecAutomation 启动器（NativeAOT）
 ---------------------------------------------------------------------
 把 Launcher.cs 编译成**原生**代码，输出到项目根目录。

 目录结构（本脚本依赖这一点）：

     分发包根\
     ├── 启动程序.exe            <- 本脚本的产物
     └── code\
         ├── run.bat  demo.py
         ├── install\
         └── tools\
             └── launcher\       <- 本脚本在这里

 NativeAOT 的好处：运行时不需要 .NET Framework / .NET 运行时，
 目标机器什么都不用装就能跑。

 前提条件：
   1. .NET SDK 8.0 或更高
   2. Visual Studio 的「使用 C++ 的桌面开发」工作负载
      （NativeAOT 需要 MSVC 的 link.exe）

 用法（在任意目录执行均可）：
   powershell -ExecutionPolicy Bypass -File build.ps1
   pwsh -NoProfile -File build.ps1

 本文件编码为 UTF-8 with BOM + CRLF，不要改为无 BOM。
 ===================================================================== #>

$ErrorActionPreference = "Continue"

# dotnet 输出是 UTF-8，显式对齐控制台编码，避免中文乱码
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "[错误] $Message" -ForegroundColor Red
    exit 1
}

$LauncherDir  = $PSScriptRoot
$ProjRoot     = (Resolve-Path (Join-Path $LauncherDir "..\..\..")).Path
$PublishDir   = Join-Path $LauncherDir "publish"
$ProjectFile  = Join-Path $LauncherDir  "Launcher.csproj"
$PubExe       = Join-Path $PublishDir   "LabSecLauncher.exe"
$OutExe       = Join-Path $ProjRoot     "启动程序.exe"

Write-Host ""
Write-Host "====================================================="
Write-Host "  编译 LabSecAutomation 启动器（NativeAOT）"
Write-Host "====================================================="
Write-Host ""

# ---- 先确认目录结构确实是新的（防止脚本被挪到别处还硬编译）----
if (-not (Test-Path (Join-Path $ProjRoot "code\run.bat"))) {
    Write-Host "[错误] 目录结构不符合预期，编译中止。" -ForegroundColor Red
    Write-Host ""
    Write-Host "  推导出的分发包根: $ProjRoot"
    Write-Host "  其中找不到:       $ProjRoot\code\run.bat"
    Write-Host ""
    Write-Host "  本脚本预期位置:   <分发包根>\code\tools\launcher\"
    Write-Host "  请确认目录结构没有被改动。"
    exit 1
}

# ---- 检查 dotnet ----
$dotnet = Get-Command dotnet -ErrorAction SilentlyContinue
if (-not $dotnet) {
    Fail ("找不到 dotnet。请先安装 .NET SDK 8.0 或更高：`r`n" +
          "       https://dotnet.microsoft.com/download")
}
Write-Host (".NET SDK 版本: " + (dotnet --version))
Write-Host ""
Write-Host "正在编译（首次编译需要联网下载，请耐心等待）..."
Write-Host ""

# 显式指定项目文件，不依赖「从哪个目录启动本脚本」
dotnet publish "$ProjectFile" -c Release -r win-x64 --nologo -v minimal -o "$PublishDir"

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Fail ("编译失败。`r`n" +
          "可能原因:`r`n" +
          "  1. 缺少 C++ 组件 —— NativeAOT 需要 MSVC 的 link.exe，`r`n" +
          "     请确认已安装 Visual Studio 的「使用 C++ 的桌面开发」工作负载。`r`n" +
          "  2. .NET SDK 版本过低，需要 8.0 或以上。`r`n" +
          "  3. 没有网络 —— NativeAOT 首次编译需要下载 ILCompiler 包。")
}

if (-not (Test-Path $PubExe)) {
    Fail ("编译完成但未找到产物: $PubExe")
}

Copy-Item $PubExe $OutExe -Force

Write-Host ""
Write-Host "[完成] 启动器已更新:"
Write-Host "       $OutExe"
Write-Host ("       大小: " + (Get-Item $OutExe).Length + " 字节")
Write-Host ""
Write-Host "提示：编译需要 .NET SDK 和 C++ 组件，接收方不需要。"
Write-Host ""

exit 0
