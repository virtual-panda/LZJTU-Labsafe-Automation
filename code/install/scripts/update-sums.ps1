<# =====================================================================
 update-sums.ps1 -- 重新生成 install\SHA256SUMS.txt 校验清单

 用法：
   powershell -ExecutionPolicy Bypass -File update-sums.ps1

 什么时候要跑：
   改动过 install\python、install\packages、install\vcruntime、
   install\scripts，或 requirements-offline.txt 之后。
   install_offline.ps1 安装时会拿这份清单做完整性自检（第 0 步），
   清单过期会导致安装包校验失败。
===================================================================== #>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallRoot = Split-Path -Parent $ScriptDir

# 生成清单前先把全部文本统一为 CRLF —— SHA256SUMS.txt 记录的是
# 「全部 CRLF」状态的哈希，与 install_offline.ps1 的自检、
# normalize_eol.ps1 三方保持一致。
& (Join-Path $ScriptDir "normalize_eol.ps1") -Quiet

# 收集要校验的文件（注意：SHA256SUMS.txt 本身不入清单）
$files = New-Object System.Collections.Generic.List[string]
foreach ($sub in @("python", "packages", "vcruntime", "scripts")) {
    $d = Join-Path $InstallRoot $sub
    if (Test-Path $d) {
        # 排除 __pycache__ / *.pyc —— 运行期产物，打包不分发，进了清单会校验失败
        Get-ChildItem $d -Recurse -File |
            Where-Object { $_.FullName -notmatch '__pycache__' -and $_.Extension -ne '.pyc' } |
            ForEach-Object { $files.Add($_.FullName) }
    }
}
$req = Join-Path $InstallRoot "requirements-offline.txt"
if (Test-Path $req) { $files.Add($req) }

$files = $files | Sort-Object

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("# LabSecAutomation 离线安装包校验清单")
$lines.Add("# 格式: <SHA256>  <相对路径>")
$lines.Add("# 生成: install\scripts\update-sums.ps1 —— 改完文件后重跑一次")
$lines.Add("")

foreach ($f in $files) {
    $rel  = $f.Substring($InstallRoot.Length + 1).Replace("\", "/")
    $hash = (Get-FileHash $f -Algorithm SHA256).Hash.ToLower()
    $lines.Add("$hash  $rel")
}

$out = Join-Path $InstallRoot "SHA256SUMS.txt"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($out, ($lines -join "`r`n") + "`r`n", $utf8NoBom)

Write-Host "已生成 SHA256SUMS.txt（$($files.Count) 个文件）: $out"
