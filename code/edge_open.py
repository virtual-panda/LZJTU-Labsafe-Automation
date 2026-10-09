"""启动 Edge 打开一个 URL，并保证新窗口是最大化的。返回新窗口的 hwnd。

为什么必须"开完之后再补一刀"：
    Edge 主进程已经在运行时，msedge.exe 只是把命令行转交给既有进程、自己随即退出，
    --start-maximized 和 -WindowStyle Maximize 都会被忽略；新窗口的大小/位置/是否最大化
    完全由 profile 里的 browser.window_placement 决定。
    所以想稳定拿到最大化窗口，只能开窗之后再用 Win32 补一刀。
"""
import subprocess
from typing import Optional

import edge_win
from advanced_print import print_pro

_EDGE_EXE = "msedge"


def _ps_quote(s: str) -> str:
    """把字符串转成 PowerShell 单引号字面量（内部的单引号用 '' 转义）。"""
    return "'" + str(s).replace("'", "''") + "'"


def open_url(url: str, new_window: bool = True,
             timeout: float = 15.0, verbose: bool = True) -> Optional[int]:
    """打开一个 URL，返回新窗口的 hwnd；没拿到新窗口就返回 None。

    new_window=True  : 新开一个窗口，并强制最大化（默认）
    new_window=False : 在当前窗口开新标签页（不会产生新窗口，返回 None）

    流程：拍快照 → 启动 → 轮询等新窗口 → 只对"本次新出现"的窗口调 Win32 最大化。
    如果同时冒出多个新窗口（比如 Edge 全新启动又恢复了上次会话），它们全都会被最大化，
    返回的是其中最后一个的 hwnd。

    本函数不抛"最大化失败"之类的异常：打开链接是主流程，不该被最大化问题拖垮；
    失败只打印告警并返回 None。
    """
    before = None
    if new_window:
        before = edge_win.snapshot()

    args = []
    if new_window:
        args.append("--new-window")
        args.append("--start-maximized")     # Edge 全新启动时有效；已在运行时会被忽略
    args.append(url)

    ps_cmd = "Start-Process {} -ArgumentList {}".format(
        _EDGE_EXE, ",".join(_ps_quote(a) for a in args))
    if new_window:
        ps_cmd += " -WindowStyle Maximize"

    # 不弹 PowerShell 黑窗（CREATE_NO_WINDOW 仅 Windows 有，做兜底）
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        ["powershell", "-NoProfile", "-Command", ps_cmd],
        creationflags=creationflags,
    )

    if not new_window or before is None:
        return None

    fresh = edge_win.wait_new_windows(before, timeout=timeout)
    if not fresh:
        if verbose:
            print_pro("[警告] {:.0f} 秒内没等到新的 Edge 窗口，本次未做最大化（链接已请求打开）。".format(timeout), color="yellow")
        return None

    last = None
    for hwnd in sorted(fresh):
        ok = edge_win.maximize(hwnd)
        if verbose:
            print_pro("  最大化窗口 hwnd={} -> {}  {}".format(
                hwnd, "成功" if ok else "失败", edge_win.describe(hwnd)))
        if ok:
            last = hwnd
    return last
