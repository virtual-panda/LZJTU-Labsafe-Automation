// =====================================================================
//  LabSecAutomation 启动器
// ---------------------------------------------------------------------
//  作用：
//    1. 自检运行环境（虚拟环境是否装好且可用）
//    2. 没装好时问用户是否现在安装，并在同一个便携终端里完成「安装 + 启动」
//    3. 环境就绪时，直接在带背景图的便携 Windows Terminal 里启动程序
//    终端不可用时（系统太旧 / 终端文件缺失），自动回退到系统默认控制台。
//
//  目录结构（本 exe 固定放在项目根）：
//
//    项目根/
//    ├── 启动程序.exe          ← 本文件（唯一需要用户双击的东西）
//    └── code/                 ← 全部代码与资源
//        ├── run.bat
//        ├── demo.py
//        ├── .venv/            安装脚本生成的虚拟环境
//        ├── install/          离线安装包
//        └── tools/            便携终端 + 本启动器源码
//
//  便携性：
//    不写死任何绝对路径，全部基于本 exe 自身位置推导，
//    项目拷到任何地方都能正常工作。
//
//  为什么编译成 WinExe？
//    WinExe 是 GUI 子系统程序，运行时 Windows 不会为它创建控制台窗口。
//    如果编译成 Console 程序，双击时会先闪一个黑框（和 .bat 一样），
//    就达不到「零闪烁」的效果了。（可用 PE 头验证：Subsystem 应为 2）
//
//  为什么用 NativeAOT 而不是普通 C#？
//    普通 C# 编译的 exe 需要目标机器上有 .NET Framework / .NET 运行时。
//    NativeAOT 直接编译成原生机器码，运行时零依赖 ——
//    目标机器什么都不用装，双击就能跑。
//
//  命令行参数：
//    /install（或 -install / --install）  强制重装环境，然后再启动程序
//    一般用户不需要，只有在怀疑环境损坏时用来手动触发重装。
//
//  编码：本文件保存为 UTF-8 with BOM + CRLF。
//        BOM 是为了让编译器和编辑器都确定按 UTF-8 解析中文字符串，
//        不要另存为 GBK，否则弹窗中文会乱码。
//
//  编译：见同目录下的 build.ps1
// =====================================================================

using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;

namespace LabSecLauncher
{
    /// <summary>
    /// 直接调用 Win32 API，这样在 NativeAOT 下也能弹出对话框
    /// （NativeAOT 不支持 WinForms，所以不能用 MessageBox.Show）。
    /// </summary>
    internal static partial class NativeMethods
    {
        private const uint MB_OK            = 0x00000000;
        private const uint MB_YESNO         = 0x00000004;
        private const uint MB_ICONERROR     = 0x00000010;
        private const uint MB_ICONQUESTION  = 0x00000020;
        private const int  IDYES            = 6;

        [LibraryImport("user32.dll", EntryPoint = "MessageBoxW",
                       StringMarshalling = StringMarshalling.Utf16)]
        private static partial int MessageBoxW(IntPtr hWnd, string lpText,
                                               string lpCaption, uint uType);

        private static int Show(string text, string caption, uint flags)
        {
            try
            {
                return MessageBoxW(IntPtr.Zero, text, caption, flags);
            }
            catch (Exception)
            {
                // 极端情况下（user32 都调不动）只能放弃弹窗
                return 0;
            }
        }

        /// <summary>弹一个错误提示框。</summary>
        public static void ShowError(string text, string caption)
        {
            Show(text, caption, MB_OK | MB_ICONERROR);
        }

        /// <summary>弹一个是/否询问框，返回用户是否选了「是」。</summary>
        public static bool AskYesNo(string text, string caption)
        {
            return Show(text, caption, MB_YESNO | MB_ICONQUESTION) == IDYES;
        }
    }

    internal static class Program
    {
        /// <summary>便携版 Windows Terminal 要求的最低系统 build 号（Win10 2004）。</summary>
        private const int MinBuildForTerminal = 19041;

        /// <summary>settings.json 里定义的专用 profile 名称。</summary>
        private const string ProfileName = "LabSecAutomation";

        /// <summary>存放全部代码的文件夹名（与本 exe 同级）。</summary>
        private const string CodeFolderName = "code";

        /// <summary>安装脚本在装好后写入的就绪标记（位于 .venv 内，随 venv 一起失效）。</summary>
        private const string ReadyStampName = ".labsec_ready";

        private static string _logPath;

        /// <summary>
        /// 排查用日志。默认关闭；设置环境变量 LABSEC_LAUNCHER_DEBUG=1 后，
        /// 会在本 exe 所在目录生成 launcher_debug.log，记录每一步的决策过程。
        /// </summary>
        private static void Log(string message)
        {
            try
            {
                if (_logPath == null) return;
                File.AppendAllText(_logPath,
                    DateTime.Now.ToString("HH:mm:ss.fff") + "  " + message + Environment.NewLine);
            }
            catch (Exception) { /* 记日志失败不影响主流程 */ }
        }

        [STAThread]
        private static int Main(string[] args)
        {
            // ---------------------------------------------------------
            // 1. 定位目录
            // ---------------------------------------------------------
            string exeDir;
            try
            {
                // 本 exe 所在目录 = 分发包根目录。
                //
                // 必须用 AppContext.BaseDirectory 而不是 Assembly.Location：
                // 本程序是单文件程序，Assembly.Location 会**永远返回空字符串**
                // （编译时有 IL3000 警告提示这一点）。
                exeDir = AppContext.BaseDirectory;
            }
            catch (Exception)
            {
                exeDir = Environment.CurrentDirectory;
            }
            exeDir = TrimDirSeparator(exeDir);

            // 调试日志（可选）
            try
            {
                if (Environment.GetEnvironmentVariable("LABSEC_LAUNCHER_DEBUG") == "1")
                {
                    _logPath = Path.Combine(exeDir, "launcher_debug.log");
                    File.WriteAllText(_logPath, "=== LabSecAutomation 启动器调试日志 ==="
                        + Environment.NewLine);
                }
            }
            catch (Exception) { _logPath = null; }

            Log("exeDir   = " + exeDir);

            string codeDir = ResolveCodeDir(exeDir);
            if (codeDir == null)
            {
                Log("中止：找不到 " + CodeFolderName + " 目录");
                NativeMethods.ShowError(
                    "找不到程序文件夹（" + CodeFolderName + "）。\r\n\r\n" +
                    "本启动器需要和 " + CodeFolderName + " 文件夹放在同一个目录里，即：\r\n\r\n" +
                    "  项目根" + Path.DirectorySeparatorChar + "\r\n" +
                    "  ├─ 启动程序.exe        ← 本文件\r\n" +
                    "  └─ " + CodeFolderName + Path.DirectorySeparatorChar + "\r\n" +
                    "      ├─ run.bat\r\n" +
                    "      └─ ...\r\n\r\n" +
                    "当前本文件所在目录：\r\n" + exeDir + "\r\n\r\n" +
                    "请确认分发包完整（不要只拷贝单个 exe），且没有改动目录名。",
                    "LabSecAutomation");
                return 1;
            }
            Log("codeDir  = " + codeDir);

            string wtExe      = Path.Combine(codeDir, "tools", "WindowsTerminal", "wt.exe");
            string runBat     = Path.Combine(codeDir, "run.bat");
            string setupBat   = Path.Combine(codeDir, "install", "scripts", "install_and_run.bat");
            string venvPython = Path.Combine(codeDir, ".venv", "Scripts", "python.exe");
            string readyStamp = Path.Combine(codeDir, ".venv", ReadyStampName);

            Log("wtExe      = " + wtExe + "   存在=" + File.Exists(wtExe));
            Log("runBat     = " + runBat + "   存在=" + File.Exists(runBat));
            Log("setupBat   = " + setupBat + "   存在=" + File.Exists(setupBat));

            if (!File.Exists(runBat) || !File.Exists(setupBat))
            {
                string missing = File.Exists(runBat) ? setupBat : runBat;
                Log("中止：缺少 " + missing);
                NativeMethods.ShowError(
                    "分发包不完整，缺少文件：\r\n\r\n" + missing + "\r\n\r\n" +
                    "请重新解压 / 重新拷贝完整的项目目录后再试。",
                    "LabSecAutomation");
                return 1;
            }

            // ---------------------------------------------------------
            // 2. 检查运行环境
            // ---------------------------------------------------------
            bool forceInstall = WantsForceInstall(args);
            string reason;
            bool ready = IsEnvironmentReady(venvPython, readyStamp, out reason);

            Log("强制安装 = " + forceInstall);
            Log("环境自检 = " + (ready ? "就绪" : "未就绪") + "   原因: " + reason);
            Log("venvPython = " + venvPython + "   存在=" + File.Exists(venvPython));
            Log("readyStamp = " + readyStamp + "   存在=" + File.Exists(readyStamp));

            // ---------------------------------------------------------
            // 3. 决定跑哪个脚本
            // ---------------------------------------------------------
            string targetBat;
            string targetDesc;

            if (ready && !forceInstall)
            {
                targetBat  = runBat;
                targetDesc = "运行程序";
            }
            else
            {
                if (!forceInstall)
                {
                    bool go = NativeMethods.AskYesNo(
                        "还没有安装运行环境，或者运行环境有问题。\r\n\r\n" +
                        "原因：" + reason + "\r\n\r\n" +
                        "点击「是」后会打开一个命令行窗口自动完成配置。这个过程无需联网，无需手动操作。\r\n" +
                        "通常 1～2 分钟，完成后会自动启动主程序。\r\n\r\n" +
                        "如果你没有 Python 3.14，会在你的用户目录下装一份独立的 Python 3.14.7，不影响你原有的 Python。\r\n\r\n" +
                        "不需要本程序时，删掉整个文件夹即可；如你不需要Python，也可在「设置-应用和功能」里单独卸载。\r\n\r\n" +
                        "开始配置吗？",
                        "LabSecAutomation");

                    Log("询问用户是否安装 -> " + (go ? "是" : "否"));
                    if (!go)
                    {
                        Log("用户选择暂不安装，退出");
                        return 0;
                    }
                }

                targetBat  = setupBat;
                targetDesc = "安装并启动";
            }

            Log("目标脚本 = " + targetBat + "   (" + targetDesc + ")");

            // ---------------------------------------------------------
            // 4. 启动
            // ---------------------------------------------------------
            int build = GetWindowsBuild();
            bool useTerminal = File.Exists(wtExe) && build >= MinBuildForTerminal;

            Log("Windows build = " + build + "  阈值=" + MinBuildForTerminal);
            Log("useTerminal = " + useTerminal);

            try
            {
                ProcessStartInfo psi;
                if (useTerminal)
                {
                    // 用便携版 WT 启动：指定 profile 和起始目录，再让它执行目标脚本
                    string arguments = string.Format(
                        "-p \"{0}\" -d \"{1}\" cmd /c \"{2}\"",
                        ProfileName, codeDir, targetBat);
                    psi = new ProcessStartInfo
                    {
                        FileName = wtExe,
                        Arguments = arguments,
                        WorkingDirectory = codeDir,
                        // 用 false：参数原样交给 CreateProcess，不经过 Shell 二次解析。
                        // 实测 UseShellExecute=true 时，带引号的多段参数会被解析错，
                        // 导致 wt.exe 静默退出、终端根本不出现。
                        UseShellExecute = false
                    };
                    Log("启动命令: \"" + wtExe + "\" " + arguments);
                }
                else
                {
                    // 降级：系统版本过低，或便携版终端文件缺失
                    psi = new ProcessStartInfo
                    {
                        FileName = targetBat,
                        WorkingDirectory = codeDir,
                        UseShellExecute = true
                    };
                    Log("降级启动: " + targetBat);
                }

                Process proc = Process.Start(psi);
                Log("Process.Start 返回: " + (proc == null ? "null" : ("PID " + proc.Id)));
                return 0;
            }
            catch (Exception ex)
            {
                Log("异常: " + ex.ToString());
                ShowError("启动失败：\r\n\r\n" + ex.Message + "\r\n\r\n" +
                          "可以尝试直接双击下面的文件作为替代方式：\r\n" + targetBat);
                return 1;
            }
        }

        /// <summary>去掉路径结尾的分隔符（BaseDirectory 结尾带一个）。</summary>
        private static string TrimDirSeparator(string dir)
        {
            if (string.IsNullOrEmpty(dir)) return dir;
            return dir.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        }

        /// <summary>
        /// 找出代码目录：一般是 &lt;exe 所在目录&gt;\code。
        /// 兜底：如果本 exe 被直接放进了代码目录里（那里有 run.bat），就用 exe 所在目录。
        /// 找不到时返回 null（调用方负责提示）。
        /// </summary>
        private static string ResolveCodeDir(string exeDir)
        {
            try
            {
                string sub = Path.Combine(exeDir, CodeFolderName);
                if (Directory.Exists(sub)) return sub;

                // 本 exe 就在代码目录里
                if (File.Exists(Path.Combine(exeDir, "run.bat"))) return exeDir;

                return null;
            }
            catch (Exception)
            {
                return null;
            }
        }

        /// <summary>是否要求强制重装（命令行参数）。</summary>
        private static bool WantsForceInstall(string[] args)
        {
            if (args == null) return false;
            foreach (string a in args)
            {
                if (string.IsNullOrEmpty(a)) continue;
                string t = a.Trim().TrimStart('/', '-').ToLowerInvariant();
                if (t == "install" || t == "reinstall" || t == "setup") return true;
            }
            return false;
        }

        /// <summary>
        /// 判断运行环境是否已经装好且可用。
        ///
        /// 三层判断，缺一不可：
        ///   1. .venv\Scripts\python.exe 存在
        ///   2. 安装脚本留下的就绪标记存在（说明依赖已完整装好并通过过验证）
        ///   3. 这个 python 真的能跑起来
        ///
        /// 第 3 条不能省：从别的机器/别的路径拷过来的 .venv，python.exe 文件还在，
        /// 但它内部记录的 Python 路径已经失效，一运行就报错。只看文件在不在会误判。
        /// </summary>
        private static bool IsEnvironmentReady(string venvPython, string readyStamp, out string reason)
        {
            if (!File.Exists(venvPython))
            {
                reason = "还没有安装过（找不到虚拟环境 .venv）";
                return false;
            }

            if (!File.Exists(readyStamp))
            {
                reason = "安装没有完成（虚拟环境缺少完成标记）";
                return false;
            }

            if (!CanRunVenvPython(venvPython))
            {
                reason = "虚拟环境无法运行（可能是从别的机器或别的路径拷过来的）";
                return false;
            }

            reason = "环境正常";
            return true;
        }

        /// <summary>
        /// 实际运行一次 venv 里的 python，确认它真的可用。
        /// 用 import sys（而不是 import cv2 等重模块）是为了够快 ——
        /// 这一步在每次启动时都会执行，不能拖慢启动。
        /// </summary>
        private static bool CanRunVenvPython(string venvPython)
        {
            try
            {
                var psi = new ProcessStartInfo
                {
                    FileName = venvPython,
                    Arguments = "-c \"import sys\"",
                    WorkingDirectory = TrimDirSeparator(Path.GetDirectoryName(venvPython)),
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true
                };

                using (Process p = Process.Start(psi))
                {
                    if (p == null) return false;

                    // 必须把输出读掉，否则子进程可能因管道写满而卡住
                    p.StandardOutput.ReadToEnd();
                    p.StandardError.ReadToEnd();

                    if (!p.WaitForExit(20000))
                    {
                        try { p.Kill(); } catch (Exception) { }
                        return false;
                    }
                    return p.ExitCode == 0;
                }
            }
            catch (Exception)
            {
                return false;
            }
        }

        /// <summary>
        /// 取当前 Windows 的 build 号（Win10 2004 = 19041、Win11 24H2 = 26100）。
        ///
        /// 为什么不用 Environment.OSVersion 直接完事？
        ///   那是 .NET Framework 的老问题 —— 程序清单没声明支持 Win8.1+ 时，
        ///   GetVersionEx 会被兼容层"骗"（返回 6.2）。但 .NET 5 起
        ///   Environment.OSVersion 已改为返回真实版本号，本程序是 NativeAOT(.NET 10)，
        ///   不存在这个坑。所以这里两条路都可用，互为兜底。
        ///
        /// 主路径：解析 RuntimeInformation.OSDescription，形如 "Microsoft Windows 10.0.26300"。
        /// 兜底  ：Environment.OSVersion.Version.Build（结构化，无字符串解析风险）。
        ///
        /// 两路都失败则返回 0 —— 宁可界面朴素（走降级分支），也不能启动不了。
        /// </summary>
        private static int GetWindowsBuild()
        {
            // ---- 主路径：解析 RuntimeInformation.OSDescription ----
            try
            {
                string osDescription = RuntimeInformation.OSDescription;
                Log("OSDescription = [" + osDescription + "]");
                if (!string.IsNullOrEmpty(osDescription))
                {
                    foreach (string token in osDescription.Split(' '))
                    {
                        if (!token.Contains(".")) continue;

                        string[] parts = token.Split('.');
                        // 需要 x.y.build 三段；少于三段时 parts[2] 会越界
                        if (parts.Length < 3) continue;

                        int parsed;
                        if (int.TryParse(parts[2], out parsed)) return parsed;
                    }
                }
            }
            catch (Exception)
            {
                // 解析失败，落到下面的兜底
            }

            // ---- 兜底：结构化 API ----
            try
            {
                int build = Environment.OSVersion.Version.Build;
                Log("主路径未解析出 build，回退到 Environment.OSVersion.Version.Build = " + build);
                if (build > 0) return build;
            }
            catch (Exception)
            {
                // 无能为力
            }

            return 0;
        }

        private static void ShowError(string message)
        {
            NativeMethods.ShowError(message, "LabSecAutomation");

            // 弹窗可能被忽略（或极端情况下失败），额外留一份文本痕迹
            try
            {
                File.WriteAllText(
                    Path.Combine(Path.GetTempPath(), "labsec_launcher_error.txt"),
                    message);
            }
            catch (Exception) { /* 无能为力 */ }
        }
    }
}
