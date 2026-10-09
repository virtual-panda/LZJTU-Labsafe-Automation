<# =====================================================================
 normalize_eol.ps1 -- 把项目内全部文本文件的行尾统一为 CRLF
 ---------------------------------------------------------------------
 本项目只面向 Windows，所有文本文件统一 CRLF：
   .bat  必须 CRLF，否则 cmd 解析出错
   .ps1  CRLF 是 Windows 习惯，避免 PS 5.1 意外
   其余文本在 Windows 平台上 CRLF 均无副作用

 什么时候会被调用（自动）：
   1. install_offline.ps1 第 0 步（checksum 自检）之前
   2. update-sums.ps1 重新生成 SHA256SUMS.txt 之前
   3. pack_dist.ps1 复制文件之前
 手动调用也可以：
   powershell -ExecutionPolicy Bypass -File normalize_eol.ps1

 设计要点：
   - 幂等：已是纯 CRLF 的文件不重写（mtime 不变）
   - 字节级处理，不经过任何编码解码（bat 是 GBK，不能按字符串读写）
   - 被重写的文件，mtime 会被重置为 -Stamp（与项目「时间戳统一」
     的隐私策略保持一致，默认 2000-01-01 00:00:00）
   - 跳过：虚拟环境、编译产物、.git、Agent 配置目录、二进制扩展名
   - SHA256SUMS.txt 记录的就是「全部 CRLF」状态的哈希，所以本脚本
     把文件拉回 CRLF 的行为，与离线安装自检是自洽的

 本文件编码为 UTF-8 with BOM + CRLF。
 ===================================================================== #>
[CmdletBinding()]
param(
    # 要规范化的根目录；默认推导为分发包根（本脚本位于 <根>\code\install\scripts\）
    [string]$Root,

    # 被重写的文件的 mtime 统一重置为该时间
    [datetime]$Stamp = [datetime]"2000-01-01 00:00:00",

    # 静默模式：只输出一行摘要（供其它脚本调用时使用）
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

if (-not $Root) {
    $Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
}
$Root = (Resolve-Path $Root).Path

# ---- 文本扩展名白名单（其它一律不碰，天然跳过 whl/exe/dll/png/gz...）----
$TextExt = @(
    ".py", ".ps1", ".bat", ".cmd",
    ".md", ".txt", ".json", ".toml", ".cfg", ".ini", ".yml", ".yaml",
    ".html", ".htm", ".cs", ".csproj", ".vbs"
)

# ---- 跳过的目录名（与 pack_dist.ps1 的排除清单保持同步）----
$SkipDirs = @(
    ".git", ".venv", "venv", "env", "ENV", "__pycache__",
    "bin", "obj", "publish", "debug",
    ".idea", ".vscode", ".workbuddy",
    ".opencode", ".mimcode", ".claude", ".codebuddy", ".cursor",
    ".windsurf", ".codeium", ".continue", ".aider", ".gemini",
    ".copilot", ".qwen", ".trae", ".roo", ".cline", ".junie", ".agents"
)

# ---- 收集文件（含无扩展名的 .gitignore / .gitattributes）----
$NoExtFiles = @(".gitignore", ".gitattributes")
$all = @(Get-ChildItem -Path $Root -Recurse -File)
$targets = New-Object System.Collections.Generic.List[string]
foreach ($f in $all) {
    $rel = $f.FullName.Substring($Root.Length + 1)
    $parts = $rel -split "\\"
    $skip = $false
    foreach ($p in $parts) {
        if ($SkipDirs -contains $p) { $skip = $true; break }
    }
    if ($skip) { continue }
    if (($TextExt -contains $f.Extension.ToLower()) -or ($NoExtFiles -contains $f.Name)) {
        $targets.Add($f.FullName)
    }
}

# ---- 逐个检查并转换（字节级，不经过编码解码）----
$changed = New-Object System.Collections.Generic.List[string]
foreach ($path in $targets) {
    $bytes = [System.IO.File]::ReadAllBytes($path)

    # 先扫一遍：有没有「前面不是 CR 的 LF」（裸 LF / LF-only 换行）
    $needFix = $false
    $prevCR = $false
    for ($i = 0; $i -lt $bytes.Length; $i++) {
        if ($bytes[$i] -eq 0x0A -and -not $prevCR) { $needFix = $true; break }
        $prevCR = ($bytes[$i] -eq 0x0D)
    }
    if (-not $needFix) { continue }   # 幂等：已是纯 CRLF（或无换行）就不动

    # 转换：每个前面不是 CR 的 LF 前面补一个 CR；已有的 CRLF 原样保留
    $out = New-Object System.Collections.Generic.List[byte]
    $prevCR = $false
    for ($i = 0; $i -lt $bytes.Length; $i++) {
        $b = $bytes[$i]
        if ($b -eq 0x0A -and -not $prevCR) { $out.Add(0x0D) }
        $out.Add($b)
        $prevCR = ($b -eq 0x0D)
    }

    [System.IO.File]::WriteAllBytes($path, $out.ToArray())
    # mtime 重置：保持项目「时间戳统一」的隐私策略不被本脚本破坏
    [System.IO.File]::SetLastWriteTime($path, $Stamp)
    $changed.Add($path.Substring($Root.Length + 1))
}

if ($Quiet) {
    Write-Output ("normalize-eol: {0} 个文本文件已统一为 CRLF（修改 {1} 个）" -f $targets.Count, $changed.Count)
    exit 0
}

Write-Host ""
Write-Host ("行尾规范化: 共检查 {0} 个文本文件" -f $targets.Count)
if ($changed.Count -eq 0) {
    Write-Host "  全部已是 CRLF，无需修改"
} else {
    Write-Host ("  已统一为 CRLF: {0} 个" -f $changed.Count)
    $changed | ForEach-Object { Write-Host ("    " + $_) }
}
Write-Host ""
exit 0
