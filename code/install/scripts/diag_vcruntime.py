# -*- coding: utf-8 -*-
"""诊断：为什么 pyclipper 的 _pyclipper 导入失败（在精简版 Windows 上）。

用法（在出问题的那台机器上，用程序自带的解释器跑）：

    双击 install\\scripts\\install.bat 装好之后，在项目根目录执行
    code\\.venv\\Scripts\\python.exe code\\install\\scripts\\diag_vcruntime.py

    或者直接把它拷到目标机，用任意 Python 3.8+ 运行。

它会做四件事：
    1. 把真实的报错原样打出来（区分「模块不存在」和「DLL 加载失败」）
    2. 检查 _pyclipper.pyd 到底在不在
    3. **逐个试加载** 这个 .pyd 依赖的每个 DLL，指出到底缺哪一个
    4. 检查系统里 VC++ 运行库的状态（注册表 + System32 文件）

只读操作，不改任何东西。
"""
import ctypes
import os
import pathlib
import struct
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def hr(title):
    print()
    print("=" * 74)
    print(title)
    print("=" * 74)


def pe_imports(path):
    """解析 PE 导入表 -> 这个 .pyd/.dll 依赖哪些 DLL。"""
    data = pathlib.Path(path).read_bytes()
    e = struct.unpack_from("<I", data, 0x3C)[0]
    if data[e:e + 4] != b"PE\0\0":
        return None
    coff = e + 4
    nsec = struct.unpack_from("<H", data, coff + 2)[0]
    optsz = struct.unpack_from("<H", data, coff + 16)[0]
    opt = coff + 20
    magic = struct.unpack_from("<H", data, opt)[0]
    ddoff = opt + (112 if magic == 0x20B else 96)
    imp_rva = struct.unpack_from("<I", data, ddoff + 8)[0]
    secoff = opt + optsz
    secs = []
    for i in range(nsec):
        b = secoff + i * 40
        vs, va, rs, rp = struct.unpack_from("<IIII", data, b + 8)
        secs.append((va, vs, rp, rs))

    def r2o(rva):
        for va, vs, rp, rs in secs:
            if va <= rva < va + max(vs, rs):
                return rp + (rva - va)
        return None

    names = []
    o = r2o(imp_rva)
    if not o:
        return names
    while True:
        ent = data[o:o + 20]
        if len(ent) < 20 or ent == b"\0" * 20:
            break
        nr = struct.unpack_from("<I", ent, 12)[0]
        if nr == 0:
            break
        no = r2o(nr)
        if no is None:
            break
        end = data.index(b"\0", no)
        names.append(data[no:end].decode("ascii", "ignore"))
        o += 20
    return names


def main():
    hr("0) 环境")
    print("  Python   :", sys.version.replace("\n", " "))
    print("  解释器   :", sys.executable)
    print("  是否 64位:", struct.calcsize("P") * 8 == 64)
    try:
        class OSVERSIONINFOEXW(ctypes.Structure):
            _fields_ = [("dwOSVersionInfoSize", ctypes.c_ulong),
                        ("dwMajorVersion", ctypes.c_ulong),
                        ("dwMinorVersion", ctypes.c_ulong),
                        ("dwBuildNumber", ctypes.c_ulong),
                        ("dwPlatformId", ctypes.c_ulong),
                        ("szCSDVersion", ctypes.c_wchar * 128)]
        info = OSVERSIONINFOEXW()
        info.dwOSVersionInfoSize = ctypes.sizeof(info)
        ctypes.windll.ntdll.RtlGetVersion(ctypes.byref(info))
        print("  系统版本 : %d.%d  内部版本 %d"
              % (info.dwMajorVersion, info.dwMinorVersion, info.dwBuildNumber))
    except Exception as exc:
        print("  系统版本 : 读不到 (%s)" % exc)
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as k:
            vals = {}
            for i in range(winreg.QueryInfoKey(k)[1]):
                n, v, _ = winreg.EnumValue(k, i)
                if n in ("ProductName", "DisplayVersion", "EditionID"):
                    vals[n] = v
            print("  产品名称 : %s" % vals.get("ProductName", "?"))
            print("  版本/版本号: %s / %s" % (vals.get("DisplayVersion", "?"),
                                            vals.get("EditionID", "?")))
    except Exception as exc:
        print("  产品名称 : 读不到 (%s)" % exc)

    # ---------------------------------------------------------------- 1
    hr("1) 直接 import pyclipper，看真实报错")
    try:
        import pyclipper
        print("  居然成功导入了：", pyclipper.__file__)
        print("  → 这台机器上 pyclipper 是好的，问题不在这里")
        return 0
    except BaseException as exc:
        print("  类型 : %s" % type(exc).__name__)
        print("  内容 : %s" % exc)
        print()
        msg = str(exc)
        if type(exc).__name__ == "ModuleNotFoundError" and "_pyclipper" in msg:
            print("  判读：**包在、但里面的 _pyclipper.pyd 不见了**")
            print("        常见原因：杀毒软件隔离了 .pyd；或安装过程中断了。")
            print("        对策：把 venv 目录加入杀软白名单，再重跑 install.bat。")
        elif type(exc).__name__ == "ModuleNotFoundError":
            print("  判读：**pyclipper 这个包整体没装**")
            print("        对策：重跑 install\\scripts\\install.bat")
        else:
            print("  判读：**文件在，但加载不起来** —— 它依赖的某个 DLL 缺失。")
            print("        第 3 步会指出到底是哪个。")

    # ---------------------------------------------------------------- 2
    hr("2) _pyclipper.pyd 在不在")
    try:
        import importlib.util
        spec = importlib.util.find_spec("pyclipper")
    except Exception as exc:
        spec = None
        print("  find_spec 出错：", exc)
    if spec is None:
        print("  ✗ 连 pyclipper 包都找不到 → 它根本没被安装")
        print("    解决：重新跑 install\\scripts\\install.bat")
        return 1
    pkg_dir = pathlib.Path(spec.origin).parent
    print("  包目录 :", pkg_dir)
    print("  包内文件:")
    pyd = None
    for p in sorted(pkg_dir.iterdir()):
        print("      %-46s %10d 字节" % (p.name, p.stat().st_size))
        if p.suffix.lower() == ".pyd":
            pyd = p
    if pyd is None:
        print("  ✗ **这个包里没有 .pyd** → 安装不完整（或被杀毒软件删了）")
        print("    解决：重新跑 install.bat（先把杀毒软件对 venv 目录排除）")
        return 1
    print("  ✓ 找到编译扩展:", pyd.name)

    # ---------------------------------------------------------------- 3
    hr("3) 逐个试加载它依赖的 DLL —— 这里能看出到底缺哪个")
    deps = pe_imports(pyd) or []
    print("  %s 依赖 %d 个 DLL:" % (pyd.name, len(deps)))
    bad = []
    for d in sorted(deps, key=str.lower):
        try:
            ctypes.WinDLL(d)
            print("      [OK]   %s" % d)
        except OSError as exc:
            bad.append((d, exc))
            print("      [失败] %-34s %s" % (d, exc))
        except Exception as exc:
            print("      [?]    %-34s %s" % (d, exc))
    print()
    if not bad:
        print("  全部依赖都能单独加载 —— 说明缺的不是整块的 DLL，")
        print("  可能是版本太旧（导出函数对不上）或位数不匹配。")
    else:
        print("  ★ 真正加载不了的是：")
        for d, exc in bad:
            print("      %s" % d)
            print("        %s" % exc)

    # ---------------------------------------------------------------- 4
    hr("3b) 顺带检查 onnxruntime —— 它排在 pyclipper 之后，缺的是同一批 DLL")
    try:
        import importlib.util as _ilu
        ospec = _ilu.find_spec("onnxruntime")
    except Exception as exc:
        ospec = None
        print("  查不到 onnxruntime:", exc)
    if ospec is None or not ospec.origin:
        print("  onnxruntime 没装（那就不存在这个问题）")
    else:
        capi = pathlib.Path(ospec.origin).parent / "capi"
        for nm in ("onnxruntime_pybind11_state.pyd", "onnxruntime.dll"):
            p = capi / nm
            if not p.is_file():
                continue
            deps = sorted(set(pe_imports(p) or []), key=str.lower)
            vc = [d for d in deps if d.upper().startswith(("MSVCP140", "VCRUNTIME140"))]
            print("  %s" % nm)
            print("      需要的 VC 运行库: %s" % (", ".join(vc) or "无"))
            for d in vc:
                try:
                    ctypes.WinDLL(d)
                    print("      [OK]   %s" % d)
                except OSError as exc:
                    bad.append((d, exc))
                    print("      [失败] %-24s %s" % (d, exc))

    # ---------------------------------------------------------------- 5
    hr("4) 系统里 VC++ 运行库的状态")
    sys32 = pathlib.Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    for n in ("vcruntime140.dll", "vcruntime140_1.dll",
              "msvcp140.dll", "msvcp140_1.dll", "ucrtbase.dll"):
        p = sys32 / n
        if p.exists():
            st = p.stat()
            print("  [有] %-22s %9d 字节  %s" % (n, st.st_size,
                                                __import__("time").strftime(
                                                    "%Y-%m-%d", __import__("time").localtime(st.st_mtime))))
        else:
            print("  [缺] %-22s  ← 系统里没有这个文件" % n)

    print()
    print("  VC++ 2015-2022 运行库注册表状态：")
    try:
        import winreg
        found = False
        for hive, path in (
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"),
        ):
            try:
                with winreg.OpenKey(hive, path) as k:
                    info = {}
                    for i in range(winreg.QueryInfoKey(k)[1]):
                        name, val, _ = winreg.EnumValue(k, i)
                        info[name] = val
                    print("      [已安装] %s" % path)
                    print("               %s" % info)
                    found = True
            except FileNotFoundError:
                pass
        if not found:
            print("      [未安装] 注册表里没有 VC++ 2015-2022 运行库的记录")
            print("               → 精简版系统上很常见，这就是根因")
    except Exception as exc:
        print("      读注册表失败:", exc)

    # ---------------------------------------------------------------- 结论
    hr("结论")
    if bad:
        print("  pyclipper 的编译扩展加载不起来，缺的是：%s"
              % "、".join(d for d, _ in bad))
        print()
        print("  修法（二选一）：")
        print("    A. 装官方 VC++ 运行库（需要管理员）")
        print("       https://aka.ms/vs/17/release/vc_redist.x64.exe")
        print("    B. 免管理员：把那几个 DLL 复制到 .pyd 旁边（同目录会被优先搜索）")
        print("       目标目录：%s" % pkg_dir)
    else:
        print("  依赖都能加载，问题可能出在别处，把上面的完整输出发回给开发者。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
