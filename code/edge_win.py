"""Edge（Chromium 系）窗口的 Win32 原语 —— 全项目唯一 import pywin32 的地方。

职责：枚举窗口 / 等新窗口 / 最大化 / 关闭 / 描述。
这里没有任何"链接""顺序""进度"之类的业务概念，所以可以单独测、单独替换。

约定：本模块的函数都不往上抛异常 —— 拿不到就返回空值（False / None / 空集合）。
窗口在枚举过程中随时可能消失，这不是异常，是常态。
"""
import ctypes
import time
from typing import List, Optional, Set

try:
    import win32api
    import win32con
    import win32gui
    import win32process

    WIN32_OK = True
    WIN32_ERROR = ""
except Exception as _exc:
    WIN32_OK = False
    WIN32_ERROR = str(_exc)

# Chromium 系浏览器顶层窗口的类名
WINDOW_CLASS = "Chrome_WidgetWin_1"
# 主进程 exe 名；注意 msedgewebview2.exe（系统"小组件"等）不算 Edge 窗口
PROCESS_NAME = "msedge.exe"
# 只要读进程映像名，这个最小权限就够
_QUERY_LIMITED = 0x1000

_user32 = None
if WIN32_OK:
    try:
        _user32 = ctypes.windll.user32     # IsZoomed 只有 user32 里有，win32gui 没导出
    except Exception:
        _user32 = None


def proc_name(hwnd: int) -> str:
    """窗口所属进程的 exe 文件名（如 msedge.exe）；取不到返回 ""。"""
    if not WIN32_OK:
        return ""
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if not pid:
            return ""
        handle = None
        try:
            handle = win32api.OpenProcess(_QUERY_LIMITED, False, pid)
            return win32process.GetModuleFileNameEx(handle, 0).split("\\")[-1]
        finally:
            if handle is not None:
                win32api.CloseHandle(handle)
    except Exception:
        return ""


def is_edge_window(hwnd: int) -> bool:
    """这个 hwnd 现在是不是一个活着的 Edge 窗口。

    用"类名 + 所属进程 exe"判断，而不是在标题里找 "Edge"：
    标题过滤既会漏（标题里没有 Edge 的 Edge 窗口），也会误伤（标题里恰好有 Edge 的其它窗口）。
    """
    if not WIN32_OK:
        return False
    try:
        if not win32gui.IsWindow(hwnd):
            return False
        if win32gui.GetClassName(hwnd) != WINDOW_CLASS:
            return False
        return proc_name(hwnd) == PROCESS_NAME
    except Exception:
        return False


def is_minimized(hwnd: int) -> bool:
    """窗口是否处于最小化状态；拿不到信息时返回 False。"""
    try:
        return bool(win32gui.IsIconic(hwnd))
    except Exception:
        return False


def is_maximized(hwnd: int) -> bool:
    """窗口是否处于最大化状态；拿不到信息时返回 False。"""
    if _user32 is None:
        return False
    try:
        return bool(_user32.IsZoomed(hwnd))
    except Exception:
        return False


def snapshot() -> Set[int]:
    """当前所有 Edge 顶层窗口的 hwnd 集合。

    刻意不判断可见性、也不判断是否最小化：Edge 进程里本来就有隐藏的顶层窗口，
    漏掉它们会被后续的"差集"误判成本次新开的窗口。
    """
    result = set()
    if not WIN32_OK:
        return result

    def collect(hwnd, _lparam):
        try:
            if win32gui.GetClassName(hwnd) == WINDOW_CLASS and proc_name(hwnd) == PROCESS_NAME:
                result.add(hwnd)
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(collect, None)
    except Exception:
        pass
    return result


def wait_new_windows(before: Set[int], timeout: float = 15.0, interval: float = 0.15) -> Set[int]:
    """等新窗口出现，返回全部"不在 before 里"的窗口 hwnd 集合；超时返回空集。

    必须轮询而不是睡固定时间：新窗口要经过"转交 → 建 renderer → 建 HWND → 显示"，
    延迟不可预测，睡短了漏、睡长了白等。
    """
    if not WIN32_OK:
        return set()

    deadline = time.time() + timeout
    while True:
        fresh = snapshot() - before
        if fresh:
            return fresh
        if time.time() >= deadline:
            return set()
        time.sleep(interval)


def wait_new_window(before: Set[int], timeout: float = 15.0, interval: float = 0.15) -> Optional[int]:
    """等一个新窗口，返回它的 hwnd；超时返回 None。"""
    fresh = wait_new_windows(before, timeout=timeout, interval=interval)
    if not fresh:
        return None
    return sorted(fresh)[0]


def maximize(hwnd: int, attempts: int = 3, wait_visible: float = 5.0) -> bool:
    """把指定窗口恢复并最大化，成功返回 True。

    Chromium 是"先建 HWND(不可见) → 再 ShowWindow"的顺序：在它显示出来之前改状态，
    会被浏览器随后的 ShowWindow 覆盖回去。所以要等"可见 + 有标题"再动手，
    改完还要校验，校验不过就重试。
    """
    if not WIN32_OK or hwnd <= 0:
        return False
    try:
        if not win32gui.IsWindow(hwnd):
            return False
    except Exception:
        return False

    deadline = time.time() + wait_visible
    while time.time() < deadline:
        try:
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                break
        except Exception:
            break
        time.sleep(0.1)

    for _ in range(attempts):
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
        except Exception:
            return False
        time.sleep(0.35)
        if is_maximized(hwnd):
            return True
    return False


def close(hwnd: int, skip_minimized: bool = False) -> bool:
    """请求关闭窗口（WM_CLOSE，等于点窗口右上角的 ×），返回是否真的发出了消息。

    注意：SW_MAXIMIZE / WM_CLOSE 这类操作直接作用在窗口上，所以调用方必须自己保证
    "只对该关的窗口调用"。本模块不做任何"帮我找出该关哪个窗口"的猜测。
    """
    if not is_edge_window(hwnd):
        return False
    if skip_minimized and is_minimized(hwnd):
        return False
    try:
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        return True
    except Exception:
        return False


def describe(hwnd: int) -> str:
    """窗口的一句话描述，用于打印；拿不到信息也不会抛异常。"""
    try:
        title = win32gui.GetWindowText(hwnd)
    except Exception:
        title = ""
    try:
        visible = bool(win32gui.IsWindowVisible(hwnd))
    except Exception:
        visible = False

    state = "普通"
    if is_minimized(hwnd):
        state = "最小化"
    elif not visible:
        state = "不可见"
    return "state={}  title={!r}".format(state, title[:50])


def list_windows(title_contains=None, visible_only: bool = True,
                 skip_minimized: bool = True) -> List[int]:
    """列出符合条件的 Edge 顶层窗口 hwnd（只查询，无副作用）。

    参数:
        title_contains: 只保留标题里包含该子串的窗口；None 表示不按标题过滤
        visible_only:   True 只保留可见窗口（默认）；False 连隐藏的一起返回
        skip_minimized: True 跳过最小化的窗口（默认）
    """
    if not WIN32_OK:
        return []

    found = []

    def collect(hwnd, _lparam):
        try:
            if win32gui.GetClassName(hwnd) != WINDOW_CLASS:
                return True
            if proc_name(hwnd) != PROCESS_NAME:
                return True
            if visible_only and not win32gui.IsWindowVisible(hwnd):
                return True
            if skip_minimized and win32gui.IsIconic(hwnd):
                return True
            if title_contains is not None:
                title = win32gui.GetWindowText(hwnd)
                if title_contains not in title:
                    return True
            found.append(hwnd)
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(collect, None)
    except Exception:
        return []
    return found
