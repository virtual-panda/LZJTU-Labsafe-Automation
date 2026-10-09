# 离线安装包使用说明

本目录是一套**完全离线**的 Python 环境安装包，用于在**无网络 / 内网 / pip 访问缓慢**的
Windows 机器上一次性装好 LabSecAutomation 所需的全部运行环境。

## 快速开始（一步）

**把整个目录拷贝到目标机器，双击：**

```
启动程序.exe
```

第一次运行它会问「是否安装运行环境」，选「是」即可。接着它会自动完成：

1. 安装 Python 3.14.7
2. 在代码目录创建虚拟环境 `.venv`
3. 把全部依赖装进 `.venv`
4. 装完立刻接着启动程序

全程不需要联网、不需要管理员权限、不需要预装 Python，约 1～2 分钟。

以后每次使用都只双击同一个 `启动程序.exe` —— 它检测到环境已就绪会直接启动，
不再询问。

> 程序会运行在一个**带背景图的现代终端**里。
> 如果终端样式很朴素（黑白边框那种），说明便携终端在当前系统上不可用
> —— 它需要 Windows 10 2004 或更高版本。启动器会自动回退到系统默认控制台，
> 功能完全一样。

### 备用方式（启动器打不开时）

```
code\install\scripts\install.bat    先装环境（只需做一次）
code\run.bat                        再启动程序
```

这两个脚本正是启动器内部实际调用的东西，手动执行效果一样。

无论走哪条路径，工作目录都会被自动切到**代码目录**（`code\`），保证
`template.png`、`textCourses.json` 这些资源文件能被正确找到
（详见下方「资源文件说明」）。

## 目录结构

```
分发包根/
├── 启动程序.exe                     ← 只需要双击这个
└── code/                            全部代码与资源
    ├── run.bat                      实际启动脚本（启动器会调用）
    ├── demo.py                      主程序
    ├── template.png                 程序需要的图片资源
    ├── template-videoCourse.png
    ├── videoCourseTarget.png
    ├── videoCourseFinished.png
    ├── textCourses.json             程序需要的课程数据
    ├── videoCourses.json
    ├── .venv/                       安装脚本生成的虚拟环境（不要手动改）
    ├── docs/
    │   └── 终端美化方案.md           终端集成方案与踩坑记录
    ├── tools/
    │   ├── WindowsTerminal/         便携版 Windows Terminal（含背景图配置）
    │   └── launcher/                启动器 C# 源码与编译脚本
    └── install/
        ├── python/
        │   └── python-3.14.7-amd64.exe  Python 官方安装程序（31.7 MB）
        ├── packages/
        │   ├── *.whl                    依赖 wheel（内部为 LZMA 压缩，见「关于 wheel 的压缩方式」）
        │   └── *.tar.gz                 少数依赖的源码包（备份用）
        ├── vcruntime/                   自带 VC++ 运行库（4 个 DLL，见「关于自带的 VC++ 运行库」）
        │   ├── msvcp140.dll
        │   ├── msvcp140_1.dll
        │   ├── vcruntime140.dll
        │   └── vcruntime140_1.dll
        ├── scripts/
        │   ├── install.bat              安装入口（可双击）
        │   ├── install_and_run.bat      「安装 → 启动」串联（启动器调用）
        │   ├── install_offline.ps1      实际安装与自检逻辑
        │   ├── pack_dist.ps1            制作分发包（维护者用）
        │   ├── update-sums.ps1          重新生成 SHA256SUMS.txt（维护者用）
        │   ├── diag_vcruntime.py        VC++ 运行库问题诊断（目标机上跑）
        │   └── get-pip.py               pip 自举备用脚本
        ├── requirements-offline.txt     锁定版本的依赖清单
        ├── SHA256SUMS.txt               全部文件的 SHA256 校验值
        └── README.md                    本文件
```

## 环境信息

| 项目 | 值 |
|---|---|
| 目标系统 | Windows x64 |
| Python 版本 | **3.14.7**（必须，见下方说明） |
| Python 安装位置 | `%LOCALAPPDATA%\Programs\Python\Python314` |
| 虚拟环境位置 | `<分发包根>\code\.venv` |
| 是否需要管理员 | **不需要**（用户级安装） |
| 是否需要联网 | **不需要** |

## 资源文件说明（重要）

`demo.py` 使用**相对路径**访问资源文件，这些路径是相对**当前工作目录（CWD）**解析的，
而不是相对脚本文件。程序运行时会用到：

| 文件 | 用途 |
|---|---|
| `template.png` | 文本课程页面的计时器模板 |
| `template-videoCourse.png` | 视频课程页面的计时器模板 |
| `videoCourseTarget.png` | 视频课程的「播放」按钮 |
| `videoCourseFinished.png` | 视频课程的「已完成」标志 |
| `textCourses.json` | 文本课程链接数据 |
| `videoCourses.json` | 视频课程链接数据 |

**这些文件必须和 `demo.py` 在同一个目录（也就是代码目录 `code\`），并且运行时工作目录必须是代码目录。**

`run.bat` 已经处理好了这一点（开头会 `cd /d "%~dp0"`），所以**请务必用「启动程序.exe」
或 `run.bat` 启动**。如果直接敲 `python demo.py`，请先自行 `cd` 到 `code\` 目录，
否则程序会报「找不到文件」。

## 脚本参数（进阶用法）

一般用户双击「启动程序.exe」即可。如有特殊需求，可在 PowerShell 里手动调用：

```powershell
# 自定义 Python 安装目录
powershell -ExecutionPolicy Bypass -File install_offline.ps1 -InstallDir "D:\Python314"

# 自定义虚拟环境位置
powershell -ExecutionPolicy Bypass -File install_offline.ps1 -VenvDir "D:\myvenv"

# 系统里已经装好 Python 3.14，跳过 Python 安装
powershell -ExecutionPolicy Bypass -File install_offline.ps1 -SkipPython
```

安装脚本是**幂等**的：每次运行都会先自检一遍（下一节详述），
已存在且可用的 `.venv` 会直接复用；依赖齐全时连 pip 都不会跑，几秒就结束。

## 完整性校验（可选）

如果对拷贝过程不放心，可以校验包是否完好：

```powershell
# 在 code\install 目录下执行
Get-ChildItem -Recurse -File | Where-Object { $_.Name -ne 'SHA256SUMS.txt' } | ForEach-Object {
    $rel = $_.FullName.Substring((Get-Location).Path.Length + 1).Replace('\','/')
    $expect = (Select-String -Path SHA256SUMS.txt -Pattern ([regex]::Escape($rel))).Line.Split(' ')[0]
    $actual = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $expect) { "不匹配: $rel" } else { "OK: $rel" }
}
```

## 注意事项

1. **必须拷贝整个分发包**，不能只拷 `install\scripts\` —— 安装程序需要
   `install\python\` 和 `install\packages\` 里的文件，`run.bat` 还需要 `code\` 下的程序文件。

2. **只需要 Python 3.14**。本离线包内的依赖（numpy / onnxruntime / pywin32 等）
   都是 `cp314` 的 wheel，只能装在 Python 3.14 上。如果目标机器上的 Python 是
   3.12 / 3.13，安装脚本会自动装一份独立的 3.14.7，不影响原有的 Python。

   ⚠️ **但要清楚它会「留下什么」**（维护者改文案 / 改行为时必须对得上）：

   脚本给 Python 安装器传的参数是
   `InstallAllUsers=0 / PrependPath=1 / Include_pip=1 / Include_launcher=1 / TargetDir=<见下>`，
   所以当它真的安装时（① 目标目录无 python.exe ② 系统未注册 3.14）：

   | 影响 | 位置 |
   |---|---|
   | 装一份独立的 Python 3.14.7 | `%LOCALAPPDATA%\Programs\Python\Python314`（**在项目文件夹之外**） |
   | 往**用户 PATH 前面**加条目（`PrependPath=1`） | 用户环境变量 `Path` |
   | 装 py 启动器（`Include_launcher=1`） | 官方安装器的用户级 launcher 目录 |

   `PrependPath=1` 的含义要说明白：**原有的其它版本 Python 文件一个都不动**，
   但它会把新装的 3.14 排到 PATH 前面 —— 所以用户以后在命令行敲 `python`，
   有可能从原来的版本变成 3.14。这是**对用户环境的一个真实改动**。

   因此「删掉项目文件夹就彻底干净」并不成立，这也是启动器弹窗里
   明确写了「不用的 Python 可在『设置-应用和功能』里单独卸载」的原因。

   > 如果不希望动用户 PATH，把 `install_offline.ps1` 里的 `PrependPath=1` 改成 `0`
   > 即可。已核实脚本默认流程**全程使用绝对路径**
   > （`$InstallDir\python.exe`、venv 内的 `python.exe`、注册表复用），
   > **并不依赖 PATH** —— 只有可选的 `-SkipPython` 是靠 PATH 查找的。
   > 改完这句「不影响你的环境」才真正字面成立。

3. **目标机器已装过 Python 3.14 时的行为**：Python 安装器无法重复注册同一版本，
   脚本会自动复用已有的解释器来创建 `.venv`。这是正常行为，不影响使用。

4. **首次运行可能被拦截**：部分杀毒软件会对静默安装行为告警，选择「允许」即可。
   本包不含任何网络请求代码。

5. **分发方式**：`install\python\` 和 `install\packages\` 加起来约 119 MB，
   已在 `.gitignore` 中排除，不适合走 git。建议用网盘、U 盘或内网共享分发。

   如果只想同步脚本部分（约 2 MB）：
   ```
   code\run.bat
   code\install\scripts\install.bat
   code\install\scripts\install_and_run.bat
   code\install\scripts\install_offline.ps1
   code\install\scripts\get-pip.py
   code\install\requirements-offline.txt
   code\install\README.md
   ```

6. **依赖已全部预构建为 wheel**：PyAutoGUI 及其附属包在 PyPI 上原本只有源码包，
   安装时需要现场编译。本离线包已经把它们的 wheel **预先构建好**放进
   `install/packages/`，因此安装时不需要 setuptools、不需要 C++ 编译器，安装更快更稳。
   原始的 `.tar.gz` 源码包仍保留作为备份。

   > 另外：这些 wheel **内部**用的是 **LZMA**（不是标准 deflate），
   > 能再省约 25 MB 体积，已实测 pip 可正常安装。
   > 详见下方「关于 wheel 的压缩方式」。

7. **重新安装 / 重来一遍**：删掉 `code\.venv` 文件夹，再双击「启动程序.exe」；
   或者在命令行执行 `启动程序.exe --install`（强制重装，跳过询问）。

## 相关文档

- [终端美化与便携化方案](../docs/终端美化方案.md)
  —— 带背景图的现代终端是怎么集成进来的、便携化原理、以及实施中踩过的坑。
  **状态：✅ 已实施**


## 关于 `.venv`（重要）

**`.venv` 是不可移植的，分发项目时请勿把它一起拷给别人。**

Python 虚拟环境会把创建时所用解释器的**绝对路径**记录在内部
（`.venv\pyvenv.cfg` 里的 `home` 项，以及 `Scripts\activate.bat` 里的 `VIRTUAL_ENV`）。
所以把 `.venv` 拷到别的机器、甚至只是拷到同一台机器的另一个目录，它都**跑不起来**，
报错形如：

```
did not find executable at 'C:\...\python.exe'
```

**正确做法**：分发时不要带上 `code\.venv`（它属于运行时产物，已在 `.gitignore`
中排除；`pack_dist.ps1` 也会自动排除并反向校验）。接收方双击「启动程序.exe」
时会被引导重新安装。

**如果你不小心把它拷过去了也不用慌** —— 自检机制会自动发现并重建。

### 自检是怎么做的（三层）

安装脚本每次运行都会按下面顺序检查现有 `.venv`，**只有确实有问题才会动手重建**：

| 层 | 检查内容 | 怎么查 | 不通过时 |
|---|---|---|---|
| ① | 能不能跑 | **实际启动一次** `python.exe -c "import sys"`，看退出码 | venv 已损坏（多半是拷来的）→ 清理重建 |
| ② | 版本对不对 | 读 venv 里的 Python 版本，必须是 3.14 | 版本不符（比如残留的 3.12 venv）→ 清理重建 |
| ③ | 依赖齐不齐 | 用 venv 的 Python 逐个 `import` 关键模块 | 缺什么补装（跑 pip）；**齐全则跳过 pip，几秒结束** |

> 第 ① 层不能省：只看 `python.exe` 文件在不在是不够的。从别的机器或别的路径
> 拷来的 venv，文件还在，但它记录的 Python 位置已经失效，一运行就报错 ——
> 只看文件存在会把它误判成「装好了」。

### 就绪标记 `.venv\.labsec_ready`

三层自检全部通过后，安装脚本会在 `.venv` 里写一个标记文件 `.labsec_ready`。
「启动程序.exe」就是靠它（外加一次快速试跑）判断环境可以直接使用、无需再询问。

标记有意放在 `.venv` **内部**：一旦 `.venv` 被删除或重建，标记自然失效，
不会出现「标记还在、环境其实已经没了」的假阳性。删掉它也没有副作用，
只是下次启动会重新自检一遍。

「启动程序.exe」的判断顺序：

1. `code\.venv\Scripts\python.exe` 存在？
2. `.venv\.labsec_ready` 存在？
3. 这个 python **真的能跑起来**？

三者都满足 → 直接启动程序；否则弹窗询问是否现在安装（在项目自带的终端里
完成「安装 → 启动」）。

## 制作分发包（维护者用）

要把项目发给别人时，**不要直接拷贝整个项目目录** —— 里面有你本地的 `code\.venv`，
它体积 300MB+，而且内部记录了创建时的绝对路径，拷到别人机器上跑不起来。

用打包脚本生成干净的分发包：

```powershell
cd code\install\scripts
powershell -ExecutionPolicy Bypass -File pack_dist.ps1
```

它会：

- 在分发包根**同级目录**生成 `<项目名>-dist-<日期>`（不写死路径，基于脚本位置推导）
- 自动排除 `code\.venv`、`__pycache__`、`debug`、`.workbuddy`、`.git`、IDE 配置，
  以及 `tools\launcher` 下的编译中间产物（`bin`/`obj`/`publish`，约 83 MB）
- 额外排除 `tools\WindowsTerminal\settings\state.json`
  （WT 的运行时状态，含本机 profile 的 GUID 列表，没必要分发）
- **校验**关键文件是否齐全、依赖 wheel 数量，并**反向确认没混进 `.venv`**
- 读 `settings.json` 里的 `backgroundImage`，确认那张背景图**确实存在**
  （改了图片文件名却忘了改配置，是最常见的「背景图不生效」原因）
- 在分发包根目录生成一份 `使用说明.txt`，接收方照着做即可

| 参数 | 作用 |
|---|---|
| `-Zip` | 额外生成 `.zip` 压缩包，方便传输 |
| `-OutputDir "D:\发布包"` | 指定输出位置 |
| `-Force` | 输出目录已存在时先删除再重建 |
| `-SkipVerify` | 跳过打包后的校验（不推荐） |

分发包体积约 **158 MB**（Python 安装器 32 MB + 依赖包 87 MB + 便携终端 35 MB）；
用 `-Zip` 压缩后约 **134 MB**（压缩率约 15%）。

输出结构就和源项目一样：`启动程序.exe` + `使用说明.txt` + `code\`。

> 打包脚本会检查分发包根下有没有「启动程序.exe」，缺了会给警告 ——
> 它是编译产物，请先在 `code\tools\launcher\` 下运行 `build.ps1` 生成。

**安全保护**：脚本会拒绝把输出目录设在分发包根或其上层目录
（因为覆盖时会先删除输出目录，路径搞错会误删源文件）。

## 关于 PowerShell 执行策略

安装流程是 `install.bat` + `install_offline.ps1` 的组合（由「启动程序.exe」
在需要时自动调用；也可以双击 `install.bat`，或用 `install_and_run.bat` 手动触发）。
**用户不需要做任何设置**，双击「启动程序.exe」或 `install.bat` 即可 ——
包括从没允许过脚本执行的电脑。

原理：`install.bat` 调用 PowerShell 时带了 `-ExecutionPolicy Bypass`。
这是**进程级**参数，只影响那一次调用（**不修改系统设置**），
但它的优先级**高于** `CurrentUser` 和 `LocalMachine` 级的策略，包括：

- `Restricted`（Windows 默认值，禁止一切脚本）
- `RemoteSigned`（本地脚本可跑，从网上下载的必须签名）

**实测记录**（本机验证，测完策略已恢复原值）：

| 场景 | 不带 Bypass | 带 `-ExecutionPolicy Bypass` |
|---|---|---|
| `RemoteSigned` + 带"下载标记"的脚本 | ❌ 未签名，拒绝加载 | ✅ 正常运行 |
| `Restricted`（完全禁止脚本） | ❌ running scripts is disabled | ✅ 正常运行 |

完整的安装流程在 `Restricted` 下实测跑通，退出码 0。

### 唯一跑不了的情况

如果电脑由**公司或学校的 IT 部门统一管控**，可能通过下面两种方式**彻底**禁止脚本：

- **组策略**（`MachinePolicy` / `UserPolicy` 级的执行策略）
- **AppLocker / WDAC**（会把 PowerShell 限制成「约束语言模式」）

它们的优先级**高于命令行参数**，`-ExecutionPolicy Bypass` 也绕不过去。
（这两种限制需要管理员或域环境才能设置，本机无法模拟复现，此处依据的是
微软官方文档中执行策略的优先级定义。）

遇到这种情况，`install.bat` 会**提前检测并给出明确提示**。
检测方式是：临时写一个只含 `exit 42` 的探针脚本，用真实调用方式执行 ——
只有脚本确实跑起来才会返回 42。

**好消息**：安装完成之后，`run.bat` **完全不依赖 PowerShell**（它直接调用
`.venv` 里的 python.exe），所以只要能装上，运行就没有任何问题。

## 关于 wheel 的压缩方式（维护者必读）

`install/packages/*.whl` **内部使用的是 LZMA（ZIP method 14）**，而不是 wheel 规范默认的
deflate（method 8）。这是有意为之，用来压缩分发包体积：

| | 大小 |
|---|---|
| 原始 wheel（内部 deflate） | 112.03 MB |
| 内部改 LZMA 后 | **87.15 MB** |
| 节省 | **24.88 MB（22.2%）** |

**为什么能省这么多**：wheel 里装的是**未压缩的**二进制（DLL / PYD），外面才套一层 deflate。
LZMA 的压缩率明显更高，而且各包差异极大：

| wheel | deflate → LZMA | 节省 |
|---|---|---|
| pillow | 6.90 → 3.96 MB | 42.6% |
| numpy | 12.01 → 8.25 MB | 31.3% |
| onnxruntime | 14.00 → 9.84 MB | 29.7% |
| opencv-python | 41.96 → 29.86 MB | 28.9% |
| pywin32 | 6.70 → 5.96 MB | 11.1% |
| **rapidocr** | 26.01 → 25.45 MB | **2.2%** ← 里面是 ONNX 浮点权重，压不动 |

**为什么不干脆全用 7z**：pip 只认 wheel，所以只能在 wheel 内部做文章。
整包改成 7z + LZMA2 固实只能再省约 7 MB（152 MB vs 159 MB），
却要求接收方装 7-Zip（Win11 24H2+ 才原生支持 7z，Win10 及更早没有），
而 zip 是 Windows 全版本原生格式 —— 不值。

**兼容性（已实测，不是推断）**：

- `pip install` 正常：真实 pip 装进干净 venv → `import` 成功
- 7-Zip 能读：产出的 ZIP 是标准格式，不是只有 Python 能读
- 35 个 wheel、共 **3163 个内部条目**，**内容哈希与原始完全一致**（只换了压缩方式）
- `SHA256SUMS.txt` 已按新文件重算

> ⚠️ 副作用：Windows 资源管理器**不能**直接打开 LZMA 压缩的 zip。
> 想手工翻看 wheel 里的文件，用 7-Zip，或
> `python -m zipfile -e <xxx.whl> <目标目录>`。

**要改回标准 wheel**：把每个 whl 的条目用 `zipfile.ZIP_DEFLATED` 逐条重写一遍即可
（内容不变），然后重算 `SHA256SUMS.txt`。

## 关于自带的 VC++ 运行库（维护者必读）

`install\vcruntime\` 里的 4 个 DLL 是**故意带的**，不是多余的文件。

### 为什么带

`pyclipper`（rapidocr 的依赖）和 `onnxruntime` 的 C 扩展**动态链接 VC++ 2015-2022
运行库**（`msvcp140.dll` 等）。这套运行库**不是 Windows 组件** —— 干净系统、
尤其是精简版系统（tiny10 实测）上没有，装官方 vcredist 又要管理员权限。
缺了它程序会在 `import pyclipper` 时报：

```
ImportError: DLL load failed while importing _pyclipper: 找不到指定的模块。
```

numpy / shapely 不受影响，因为它们的 wheel **自带**了一份改名版的运行库
（`numpy.libs\msvcp140-<hash>.dll`，delvewheel 机制）；cv2 是静态链接，完全不依赖。
唯独 pyclipper / onnxruntime 的 wheel 什么都不带。

### 怎么工作的（安装时第 4 步）

安装脚本把 4 个 DLL 复制进 venv 的 `site-packages\_vcruntime\`，并生成两个文件：

- `_labsec_vcrt.pth` —— 内容只有一行 `import _labsec_vcrt`，
  Python 每次启动处理 .pth 时会执行它；
- `_labsec_vcrt.py` —— 补丁模块，用 `__file__` 推导出 `_vcruntime\` 的位置，
  调 `os.add_dll_directory()` 把它加入 DLL 搜索路径。

这与 numpy / shapely 的 delvewheel 机制**完全相同**。自带目录优先于 System32，
所以即使接收方的系统里有（可能更旧的）运行库，用的也是我们这份，行为一致。

### 维护注意

- **不要删** `_vcruntime\`、`.pth`、`.py` 三样；删了精简系统上必挂。
- 想升级 DLL：从一台装好了新版 vcredist 的机器上，把 `C:\Windows\System32\`
  里这 4 个文件拷过来覆盖，然后重跑 `install\scripts\update-sums.ps1`，
  最后重新打包。
- 诊断工具：`install\scripts\diag_vcruntime.py`，拷到目标机用
  `code\.venv\Scripts\python.exe` 跑，能定位到底是缺 DLL 还是 .pyd 被杀了。
- 关于「官方 vcredist 占多少」与「为什么不装它」：安装包 24.45 MB、装完实际新增
  约 27.8 MB（含 C:\Windows\Installer 缓存）、且要管理员 —— 自带 DLL 只有 887 KB。

## 关于日志颜色（维护者必读）

程序面向用户的日志**全部走 `advanced_print.print_pro`**，不再用原生 `print`。
配色是逐条选定的，出处与完整清单见 `code\tools\log-colors\`（`colors.json` 就是那张表）。

### 配色约定

| 类别 | 颜色 | 典型例子 |
|---|---|---|
| 阶段切换（关键节点） | **青** + 时间戳 | 「开刷视频课喵」 |
| 进度数据（关键节点） | **青** + 时间戳 | 「已学时长：07:12，要求时长：45:00」 |
| 成功 / 完成 | **绿** | 「本节已学完，请等待数据上传…」 |
| 警告 | **黄** | 「没找到计时器喵」 |
| 错误 | **红** | 「模板文件不可用：…」 |
| 过程提示、输入回显 | 无色（终端默认前景） | 「正在等待页面加载…」 |
| verbose 调试明细 | 无色 | `click_by_image` 的 `[信息] …` 行 |

### 改动日志时必须知道的 4 件事

1. **只吃一个位置参数**：`print_pro(content, timestamp=False, color=None)`。
   原来的 `print(a, b, c)` 必须改成单个 f-string。
2. ⚠️ **`print` 会自动在参数之间补一个空格**，改 f-string 时要把它补回来，
   否则输出文本会**悄悄变样**。例：
   `print("正在打开：", name, "URL: ", url)` → `print_pro(f"正在打开： {name} URL:  {url}")`
   （`URL: ` 自带一个尾空格，再加 print 的分隔空格 = 两个）
3. **没有 `file=` 参数**：所以 `click_by_image.py` 里两处原本走 **stderr** 的严重警告
   （坐标系不一致、匹配分数过低）现在走 **stdout**。via `run.bat` 运行时两者都进同一个终端，
   肉眼无差别；但**如果将来有人重定向 stderr 抓错误日志，这两条不会再出现**。
4. **没有 `flush` 参数**：`locate_and_ocr.log()` 原来靠 `flush=True` 保证
   `--watch` 模式实时输出，现在改成 `print_pro(message)` 后**补一句 `sys.stdout.flush()`**。
   改这个函数时别把 flush 弄丢。

### 颜色在终端里的真实样子

终端配色方案是 **One Half Dark**（见 `code\tools\WindowsTerminal\settings\settings.json`），
ANSI 颜色会被它**重映射** —— `\033[31m` 渲染成 `#E06C75` 而不是纯红。真实色值取自
WT 自带的 `defaults.json`。

| 代码里的名字 | 实际渲染色 |
|---|---|
| red | `#E06C75` |
| green | `#98C379` |
| yellow | `#E5C07B` |
| blue | `#61AFEF` |
| magenta | `#C678DD` |
| cyan | `#56B6C2` |
| white | `#DCDFE4`（**= 默认前景色，选它等于没上色**） |
| gray | `#5A6374` |
| black | `#282C34`（**= 背景色，选它等于看不见 —— 别用**） |

### 想改颜色

打开 `code\tools\log-colors\index.html`（单文件网页，双击即可），
逐条点选颜色 / 勾时间戳，导出 JSON 覆盖 `code\tools\log-colors\colors.json`，
再按那张表改代码即可 —— 页面里的终端预览用的就是上面这套真实色值。

## 关于文件编码

这套脚本踩过编码的坑，改动时请务必保持现状，否则会遇到
「不是内部或外部命令」这类莫名其妙的报错。

| 文件 | 编码 | 换行 | 原因 |
|---|---|---|---|
| `code\run.bat` | **GBK (936)** | **CRLF** | cmd 用系统代码页解析 bat，UTF-8 中文会被误解析；LF 换行会导致字节错乱 |
| `code\install\scripts\install.bat` | **GBK (936)** | **CRLF** | 同上 |
| `code\install\scripts\install_and_run.bat` | **GBK (936)** | **CRLF** | 同上 |
| `code\install\scripts\install_offline.ps1` | **UTF-8 with BOM** | CRLF | PowerShell 5.1 靠 BOM 识别 UTF-8 中文 |
| `code\install\scripts\pack_dist.ps1` | **UTF-8 with BOM** | CRLF | 同上 |
| `code\install\scripts\update-sums.ps1` | **UTF-8 with BOM** | CRLF | 同上 |
| `code\tools\launcher\build.ps1` | **UTF-8 with BOM** | CRLF | 同上（启动器编译脚本） |
| `code\tools\launcher\Launcher.cs` | **UTF-8 with BOM** | CRLF | BOM 让编译器和编辑器都确定按 UTF-8 解析中文字符串（弹窗文案） |
| Python 源码 | UTF-8 | — | 常规做法 |

**代码页的配合方式**：

- bat 内部用 `chcp 936`，让 bat 自己的中文提示正常显示
- `run.bat` 在**启动 Python 之前**切到 `chcp 65001`，跑完再切回 `936`
  —— 因为 `demo.py` 内部把 stdout 设成了 UTF-8，代码页必须匹配，否则日志乱码
- `install_offline.ps1` **不强制设置**输出编码，跟随调用方的代码页

**另外注意**：`code\` 下有 `.gitattributes`，已声明 `*.bat text eol=crlf`。
请不要删除它，否则 git 在 checkout 时可能把 bat 的 CRLF 转成 LF，脚本就坏了。

> ⚠️ 目录调整后这两个文件的位置需要注意：`.gitignore` / `.gitattributes` 目前在
> `code\` 下，而 `启动程序.exe` 在分发包根。如果要把**整个分发包根**作为 git 仓库，
> 建议把它们挪到根部，否则根目录下的 `启动程序.exe`（编译产物）不会被忽略。

