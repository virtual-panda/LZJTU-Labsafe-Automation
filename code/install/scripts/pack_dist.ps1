<#
=====================================================================
 LabSecAutomation 分发包制作脚本
---------------------------------------------------------------------
 作用：
   把项目复制成一个干净的、可以直接发给别人的目录，
   自动排除 .venv、__pycache__、debug 等不该分发的内容。

 产出结构（与源项目一致，接收方直接能用）：

   分发包根\
   ├── 启动程序.exe            接收方只双击这个
   ├── 使用说明.txt            自动生成
   └── code\                   全部代码、资源与离线安装包

 为什么要专门做这个？
   .venv 是本地虚拟环境，体积大（300M+），而且内部记录了创建时的
   绝对路径，拷给别人是跑不起来的。分发包里绝不能带上它。
   手工复制很容易漏掉这一点，所以用脚本固化下来。

 用法（ps1 无法双击，请在 PowerShell 里执行）：
   powershell -ExecutionPolicy Bypass -File pack_dist.ps1

   常用变体：
   powershell -ExecutionPolicy Bypass -File pack_dist.ps1 -Zip
   powershell -ExecutionPolicy Bypass -File pack_dist.ps1 -OutputDir "D:\发布包"

 参数：
   -OutputDir <路径>  指定输出目录
                      （默认：项目根同级目录下的 <项目名>-dist-<日期>）
   -Zip               额外生成一个 .zip 压缩包，方便传输
   -Force             输出目录已存在时，先删除再重新生成
   -SkipVerify        跳过打包后的完整性校验（不推荐）

 说明：
   脚本不写死任何绝对路径，全部基于自身位置推导，
   因此项目搬到任何地方都能正常使用。
=====================================================================
#>

[CmdletBinding()]
param(
    [string]$OutputDir = "",
    [switch]$Zip,
    [switch]$Force,
    [switch]$SkipVerify
)

# ---------------------------------------------------------------
# 全局设置
# ---------------------------------------------------------------
$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

# ---------------------------------------------------------------
# 输出辅助函数
# ---------------------------------------------------------------
function Write-Step { param([string]$m) Write-Host ""; Write-Host "==== $m ====" -ForegroundColor Cyan }
function Write-Ok   { param([string]$m) Write-Host "  [OK]   $m" -ForegroundColor Green }
function Write-Info { param([string]$m) Write-Host "  [..]   $m" -ForegroundColor Gray }
function Write-Warn { param([string]$m) Write-Host "  [警告] $m" -ForegroundColor Yellow }
function Write-Err  { param([string]$m) Write-Host "  [错误] $m" -ForegroundColor Red }

function Stop-WithError {
    param([string]$Message)
    Write-Host ""
    Write-Err $Message
    Write-Host ""
    Write-Host "打包已中止。" -ForegroundColor Red
    if (-not $env:LABSEC_NO_PAUSE) {
        Write-Host "按任意键关闭..." -ForegroundColor Gray
        try { $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown") } catch { }
    }
    exit 1
}

# 把字节数转成人类可读
function Format-Size {
    param([double]$Bytes)
    if ($Bytes -ge 1GB) { return ("{0:N2} GB" -f ($Bytes / 1GB)) }
    if ($Bytes -ge 1MB) { return ("{0:N2} MB" -f ($Bytes / 1MB)) }
    if ($Bytes -ge 1KB) { return ("{0:N2} KB" -f ($Bytes / 1KB)) }
    return ("{0:N0} B" -f $Bytes)
}

# ---------------------------------------------------------------
# 路径推导（不写死任何绝对路径）
# ---------------------------------------------------------------
# 目录结构（本脚本在最后一层）：
#   分发包根\                        ← $ProjRoot（要整体分发的内容）
#     ├── 启动程序.exe
#     └── code\                      ← $CodeDir
#           ├── run.bat  demo.py  资源文件
#           ├── .venv\               （绝不分发）
#           └── install\scripts\     ← 本脚本在这里
$ScriptDir   = $PSScriptRoot                                  # <根>\code\install\scripts
$InstallRoot = Split-Path -Parent $ScriptDir                  # <根>\code\install
$CodeDir     = Split-Path -Parent $InstallRoot                # <根>\code
$ProjRoot    = Split-Path -Parent $CodeDir                    # <根>（分发包根）
$ProjectName = Split-Path -Leaf $ProjRoot

if (-not (Test-Path (Join-Path $CodeDir "demo.py"))) {
    Stop-WithError "看起来这里不是预期的项目目录。`n  推导出的代码目录: $CodeDir`n  其中找不到 demo.py。`n请确认本脚本位于 <分发包根>\code\install\scripts\ 目录下。"
}

if (-not (Test-Path (Join-Path $ProjRoot "启动程序.exe"))) {
    Write-Warn "分发包根下找不到「启动程序.exe」：$ProjRoot"
    Write-Warn "打出来的包会缺少这个小启动器，接收方只能双击 code\run.bat。"
    Write-Warn "请先在 code\tools\launcher\ 下运行 build.ps1 生成它。"
}

# 默认输出目录：分发包根同级，带日期，避免覆盖
if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $ParentDir = Split-Path -Parent $ProjRoot
    $Stamp     = Get-Date -Format "yyyyMMdd"
    $OutputDir = Join-Path $ParentDir "$ProjectName-dist-$Stamp"
}

$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$ProjRoot  = [System.IO.Path]::GetFullPath($ProjRoot)

# ---------------------------------------------------------------
# 安全检查：绝不能把输出目录设在分发包内部或它的上层
# （后面会删掉已存在的输出目录，路径搞错会误删源文件）
# ---------------------------------------------------------------
if ($OutputDir -eq $ProjRoot) {
    Stop-WithError "输出目录不能是分发包根目录本身：`n  $OutputDir"
}
if ($ProjRoot.StartsWith($OutputDir + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    Stop-WithError "输出目录不能是分发包根的上层目录（删除它会连源文件一起删掉）：`n  输出: $OutputDir`n  源  : $ProjRoot"
}
if ($OutputDir.StartsWith($ProjRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    Write-Warn "输出目录在项目内部，虽然能工作，但建议放到项目外面。"
}

# ---------------------------------------------------------------
# 排除清单
# ---------------------------------------------------------------
# 目录：按名字匹配任意层级
$ExcludeDirs = @(
    ".venv", "venv", "env", "ENV",       # 虚拟环境（重点：绝不分发）
    "__pycache__",                        # Python 字节码缓存
    ".git",                               # 版本库
    ".idea", ".vscode",                   # IDE 配置
    "debug",                              # 程序运行时的调试输出
    "bin", "obj", "publish",              # .NET / NativeAOT 编译中间产物（很大，不要分发）
    "*.egg-info",

    # -----------------------------------------------------------
    # AI / Agent 工具的配置与工作目录（都是本机开发痕迹，不该分发）
    # 名单按「常见程度」维护，遇到新的往里加即可
    # -----------------------------------------------------------
    ".opencode",                          # OpenCode
    ".mimcode",                           # Mimicode
    ".claude",                            # Claude Code
    ".workbuddy",                         # WorkBuddy
    ".codebuddy",                         # CodeBuddy
    ".cursor",                            # Cursor
    ".windsurf", ".codeium",              # Windsurf / Codeium
    ".continue",                          # Continue
    ".aider",                             # Aider
    ".gemini",                            # Gemini CLI
    ".copilot",                           # GitHub Copilot CLI
    ".qwen",                              # Qwen Code
    ".trae",                              # Trae
    ".roo",                               # Roo Code
    ".cline",                             # Cline
    ".junie",                             # JetBrains Junie
    ".agents"                             # 通用 Agent 配置
)

# 文件：按通配符匹配
$ExcludeFiles = @(
    "state.json",                         # WT 的运行时状态：含本机 profile GUID，不该分发
    "*.pyc", "*.pyo",
    "*.log",
    "Thumbs.db", "Desktop.ini", ".DS_Store",
    "screenshot_*.png",

    # AI / Agent 工具的散装配置文件（与上面的目录配套）
    "AGENTS.md", "CLAUDE.md", ".clinerules",
    ".cursorrules", ".cursorignore", ".windsurfrules",
    ".aider*", ".mcp.json", ".opencode.json"
)

# ---------------------------------------------------------------
# 横幅
# ---------------------------------------------------------------
Write-Host ""
Write-Host "=====================================================" -ForegroundColor White
Write-Host "  LabSecAutomation  分发包制作" -ForegroundColor White
Write-Host "=====================================================" -ForegroundColor White
Write-Host ""
Write-Info "分发包根   : $ProjRoot"
Write-Info "代码目录   : $CodeDir"
Write-Info "输出目录   : $OutputDir"
Write-Info "排除目录   : $($ExcludeDirs -join ', ')"
Write-Host ""

# ---------------------------------------------------------------
# 1. 准备输出目录
# ---------------------------------------------------------------
Write-Step "1/4 准备输出目录"

if (Test-Path $OutputDir) {
    if ($Force) {
        Write-Info "输出目录已存在，按 -Force 要求先清空"
        Remove-Item -Path $OutputDir -Recurse -Force
    } else {
        Stop-WithError @"
输出目录已存在:
  $OutputDir

如果确定要覆盖，请加上 -Force 参数重跑，例如：
  powershell -ExecutionPolicy Bypass -File pack_dist.ps1 -Force

或者用 -OutputDir 指定另一个位置。
"@
    }
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
Write-Ok "输出目录就绪"

# ---------------------------------------------------------------
# 2. 复制文件
# ---------------------------------------------------------------
Write-Step "2/4 复制项目文件"

# 复制前把全部文本文件统一为 CRLF：分发包内的行尾状态与
# SHA256SUMS.txt 的自检基准保持一致，也保证 .bat 永远可双击。
& (Join-Path $ScriptDir "normalize_eol.ps1") -Root $ProjRoot -Quiet

# 优先用 robocopy：它处理大量小文件比 Copy-Item 快很多，
# 而且原生支持排除目录/文件。
$roboArgs = @(
    $ProjRoot,
    $OutputDir,
    "/E",                    # 含子目录，包括空目录
    "/XD"
) + $ExcludeDirs + @(
    "/XF"
) + $ExcludeFiles + @(
    "/R:1",                  # 失败重试 1 次
    "/W:1",                  # 重试间隔 1 秒
    "/NFL",                  # 不逐条列出文件名
    "/NDL",                  # 不列出目录名
    "/NP"                    # 不显示百分比进度
)

Write-Info "正在复制（约 145 MB，请稍候）..."
$null = & robocopy @roboArgs
$roboRc = $LASTEXITCODE

# robocopy 的退出码：0-7 都算成功（1=有文件被复制，3=1+2 等），>=8 才是错误
if ($roboRc -ge 8) {
    Stop-WithError "复制过程中出错（robocopy 退出码 $roboRc）。`n请检查目标磁盘空间和写入权限。"
}
Write-Ok "复制完成（robocopy 退出码 $roboRc）"

# ---------------------------------------------------------------
# 3. 生成给接收方的使用说明
# ---------------------------------------------------------------
Write-Step "3/4 生成使用说明"

$usageText = @"
========================================================
 LabSecAutomation  使用说明
========================================================

这个文件夹里包含了程序和全部运行环境，不需要联网。

--------------------------------------------------------
 怎么用（只需一步）
--------------------------------------------------------

  双击：

      启动程序.exe

  第一次运行它会问你「是否安装运行环境」，选「是」。
  接着它会自动完成：
    1. 安装 Python 3.14.7
    2. 创建虚拟环境
    3. 安装全部依赖
    4. 装完后自动接着启动程序

  全程离线、不需要管理员权限，大约 1～2 分钟。
  如果杀毒软件弹窗提示，选择「允许」即可。

  以后每次使用都只需要双击同一个「启动程序.exe」——
  它检测到环境已经装好，会直接启动，不再询问。

  程序会运行在一个带背景图的现代终端里。


--------------------------------------------------------
 如果启动器打不开
--------------------------------------------------------

  可以直接双击：

      code\run.bat

  功能完全一样，只是界面朴素些（系统默认控制台）。
  首次使用请先跑一次 code\install\scripts\install.bat 把环境装好。


--------------------------------------------------------
 常见问题
--------------------------------------------------------

  Q: 弹窗问是否安装环境，可以选「否」吗？
  A: 可以，但环境没装好就没法运行程序，下次双击还会再问一次。

  Q: 想重装一遍环境？
  A: 删掉 code\.venv 文件夹，再双击「启动程序.exe」。
     或者在命令行里执行：启动程序.exe --install

  Q: 双击「启动程序.exe」没反应？
  A: 直接双击 code\run.bat 作为替代，功能完全一样。
     想知道失败原因，可以先设置环境变量 LABSEC_LAUNCHER_DEBUG=1
     再运行一次，项目根目录会生成 launcher_debug.log 记录详细过程。

  Q: 终端样式很朴素（黑白边框那种），没有背景图？
  A: 说明这个便携终端在当前系统上不可用（需要 Windows 10 2004 或更高）。
     启动器已经自动回退到系统默认控制台，功能不受影响。

  Q: 想换终端的背景图？
  A: 把自己的图片放进 code\tools\WindowsTerminal\settings\ 目录，
     然后编辑同目录的 settings.json，把
         "backgroundImage": "bg.png"
     改成你的文件名（建议 1920x1080 的 jpg/png）。
     嫌背景太抢眼就把 "backgroundImageOpacity" 调小（0.2~0.5 比较合适）。

  Q: 提示「系统禁止运行 PowerShell 脚本」？
  A: 这是电脑被公司/学校统一管控了。详见
     code\install\README.md 里的「关于 PowerShell 执行策略」。


--------------------------------------------------------
 目录说明
--------------------------------------------------------

  启动程序.exe              双击这个就行
  code\                     全部代码与资源都在这里
    ├── run.bat             实际启动脚本（备用入口）
    ├── demo.py             主程序
    ├── .venv\              安装脚本生成的运行环境
    ├── install\            离线安装包
    └── tools\              便携终端 + 启动器源码


--------------------------------------------------------
 更多信息
--------------------------------------------------------

  详细说明请查看：code\install\README.md

  本项目依赖 Python 3.14，请勿把 code\.venv 文件夹单独拷来拷去 ——
  虚拟环境内部记录了创建时的绝对路径，换地方就失效。
  （不过就算拷错了也不要紧，安装脚本会自动检测并重建）

========================================================
"@

$usagePath = Join-Path $OutputDir "使用说明.txt"
# 用 UTF-8 with BOM 写入，保证 Windows 记事本打开不乱码
$utf8Bom = New-Object System.Text.UTF8Encoding($true)
[System.IO.File]::WriteAllText($usagePath, $usageText, $utf8Bom)
Write-Ok "已生成: 使用说明.txt"

# ---------------------------------------------------------------
# 4. 校验 + 统计
# ---------------------------------------------------------------
Write-Step "4/4 校验分发包"

$problem = 0

if (-not $SkipVerify) {
    # 4a. 必须存在的关键文件（路径相对分发包根）
    $required = @(
        "启动程序.exe",
        "使用说明.txt",
        "code\run.bat",
        "code\demo.py",
        "code\advanced_print.py",
        "code\click_by_image.py",
        "code\edge_open.py",
        "code\edge_win.py",
        "code\find_edge.py",
        "code\link_cursor.py",
        "code\locate_and_ocr.py",
        "code\read_and_open_link.py",
        "code\install\scripts\install.bat",
        "code\install\scripts\install_offline.ps1",
        "code\install\scripts\install_and_run.bat",
        "code\install\vcruntime\msvcp140.dll",
        "code\install\vcruntime\msvcp140_1.dll",
        "code\install\vcruntime\vcruntime140.dll",
        "code\install\vcruntime\vcruntime140_1.dll",
        "code\install\requirements-offline.txt",
        "code\install\README.md",
        "code\tools\WindowsTerminal\wt.exe",
        "code\tools\WindowsTerminal\.portable",
        "code\tools\WindowsTerminal\settings\settings.json",
        "code\template.png",
        "code\template-videoCourse.png",
        "code\videoCourseTarget.png",
        "code\videoCourseFinished.png",
        "code\textCourses.json",
        "code\videoCourses.json"
    )

    $missing = @()
    $softMissing = @()   # 源目录本来就没有 → 警告而非错误
                         # （如 git clone 场景：启动程序.exe 不入库、便携终端被忽略）
    foreach ($rel in $required) {
        if (-not (Test-Path (Join-Path $OutputDir $rel))) {
            if (Test-Path (Join-Path $ProjRoot $rel)) { $missing += $rel }
            else { $softMissing += $rel }
        }
    }
    if ($softMissing.Count -gt 0) {
        Write-Warn "以下文件源目录就不存在（clone 后未编译/未获取），分发包将缺少它们:"
        $softMissing | ForEach-Object { Write-Host "         $_" -ForegroundColor Yellow }
        Write-Warn "不影响安装与基本使用；需要时用 build.ps1 编译启动器、按文档获取便携终端。"
    }
    if ($missing.Count -gt 0) {
        Write-Err "缺少关键文件（源目录有、分发包没有 —— 复制出了问题）:"
        $missing | ForEach-Object { Write-Host "         $_" -ForegroundColor Red }
        $problem++
    }
    if ($missing.Count -eq 0) {
        Write-Ok "关键文件齐全（$($required.Count) 项，其中 $($softMissing.Count) 项源缺失已警告）"
    }

    # 4a-2. 终端背景图
    # 背景图的文件名不固定（可以自己换成任意图片），所以不能硬编码检查某个文件名，
    # 而是读 settings.json 里写的 backgroundImage，验证那个文件确实存在 ——
    # 名字改了却忘了改配置，是最常见的"背景图不生效"原因。
    $settingsDir  = Join-Path $OutputDir "code\tools\WindowsTerminal\settings"
    $settingsFile = Join-Path $settingsDir "settings.json"
    if (Test-Path $settingsFile) {
        try {
            $cfg = [System.IO.File]::ReadAllText($settingsFile, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
            $bgName = $cfg.profiles.defaults.backgroundImage
            if ($bgName) {
                $bgPath = Join-Path $settingsDir $bgName
                if (Test-Path $bgPath) {
                    Write-Ok "终端背景图: $bgName ($(Format-Size (Get-Item $bgPath).Length))"
                } else {
                    Write-Err "settings.json 指定的背景图不存在: $bgName（终端会退化成纯色背景）"
                    $problem++
                }
            } else {
                Write-Info "settings.json 没设置 backgroundImage（纯色终端，属正常配置）"
            }
        } catch {
            Write-Warn "解析 settings.json 检查背景图时出错: $($_.Exception.Message)"
        }
    }

    # 4b. 离线安装包
    $pyExes = @(Get-ChildItem -Path (Join-Path $OutputDir "code\install\python") -Filter "*.exe" -File -ErrorAction SilentlyContinue)
    if ($pyExes.Count -eq 0) {
        Write-Err "code\install\python\ 下找不到 Python 安装程序"
        $problem++
    } else {
        Write-Ok "Python 安装程序: $($pyExes[0].Name) ($(Format-Size $pyExes[0].Length))"
    }

    $whlCount = @(Get-ChildItem -Path (Join-Path $OutputDir "code\install\packages") -Filter "*.whl" -File -ErrorAction SilentlyContinue).Count
    if ($whlCount -lt 30) {
        Write-Err "依赖包不完整，只找到 $whlCount 个 wheel（预期 35 个左右）"
        $problem++
    } else {
        Write-Ok "依赖 wheel: $whlCount 个"
    }

    # 4c. 反向校验：绝不能包含 .venv（这是本脚本存在的主要理由）
    if (Test-Path (Join-Path $OutputDir "code\.venv")) {
        Write-Err "分发包里混进了 .venv！它体积大且换机器就失效，必须排除。"
        $problem++
    } else {
        Write-Ok "已确认不含 .venv"
    }

    if (Test-Path (Join-Path $OutputDir "code\__pycache__")) {
        Write-Warn "分发包里还有 __pycache__（不影响使用，但没必要）"
    }
}

# 统计
$allFiles = @(Get-ChildItem -Path $OutputDir -Recurse -File -ErrorAction SilentlyContinue)
$totalSize = ($allFiles | Measure-Object -Property Length -Sum).Sum
if (-not $totalSize) { $totalSize = 0 }

Write-Host ""
Write-Info "文件总数: $($allFiles.Count)"
Write-Info "总大小  : $(Format-Size $totalSize)"

# ---------------------------------------------------------------
# 可选：压缩
# ---------------------------------------------------------------
$zipPath = ""
if ($Zip) {
    Write-Host ""
    Write-Info "正在压缩（大文件较多，可能需要一会儿）..."
    $zipPath = "$OutputDir.zip"
    if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

    # 用 .NET 的 ZipFile.CreateFromDirectory，而不是 Compress-Archive：
    #   includeBaseDirectory = $true → 压缩包里带一层外层文件夹名。
    #   否则（Compress-Archive -Path "$OutputDir\*"）压出来没有外层目录，
    #   接收方用「解压到当前文件夹」会把 code\ 和 启动程序.exe 直接撒在下载目录里。
    #   另外 CreateFromDirectory 会带上隐藏文件（.portable 标记就在其中）。
    try { Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction Stop }
    catch { }   # PowerShell 7 自带，不需要显式加载
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $OutputDir,
        $zipPath,
        [System.IO.Compression.CompressionLevel]::Optimal,
        $true)

    if (Test-Path $zipPath) {
        $zipSize = (Get-Item $zipPath).Length
        Write-Ok "压缩包: $zipPath ($(Format-Size $zipSize))"
    } else {
        Write-Warn "压缩似乎没有成功，但文件夹已经生成好了，可以直接用。"
        $zipPath = ""
    }
}

# ---------------------------------------------------------------
# 完成
# ---------------------------------------------------------------
Write-Host ""
if ($problem -gt 0) {
    Write-Host "=====================================================" -ForegroundColor Yellow
    Write-Host "  打包完成，但校验发现 $problem 个问题（见上方红色提示）" -ForegroundColor Yellow
    Write-Host "=====================================================" -ForegroundColor Yellow
} else {
    Write-Host "=====================================================" -ForegroundColor Green
    Write-Host "  打包完成！" -ForegroundColor Green
    Write-Host "=====================================================" -ForegroundColor Green
}
Write-Host ""
Write-Host "  分发包位置: $OutputDir" -ForegroundColor White
if ($zipPath) {
    Write-Host "  压缩包    : $zipPath" -ForegroundColor White
}
Write-Host ""
Write-Host "  接收方拿到后，双击「启动程序.exe」即可（首次会引导安装运行环境）。" -ForegroundColor Yellow
Write-Host ""

if (-not $env:LABSEC_NO_PAUSE) {
    Write-Host "按任意键关闭..." -ForegroundColor Gray
    try { $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown") } catch { }
}

exit 0
