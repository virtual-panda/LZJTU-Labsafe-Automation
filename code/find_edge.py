"""按 hwnd 精确关闭 Edge 窗口 —— 不做无差别关闭。

窗口的枚举和关闭全部由 edge_win 提供；本模块只负责"确认这是不是要关的那个窗口"，
从不自己去猜关闭范围。

为什么没有"关闭所有 Edge 窗口"这种功能：
    WM_CLOSE 等同于用户点窗口右上角的 ×。无差别扫一遍会把用户自己开着的窗口一起关掉，
    多标签窗口还可能弹"关闭全部标签页?"确认框 —— 那是不可接受的风险。

用法：
    import find_edge

    # 只列出，不动任何窗口
    for hwnd in find_edge.find_edge_windows():
        print(hwnd, find_edge.describe_window(hwnd))

    # 精确关闭（hwnd 从哪来由你决定，比如 opener.hwnd）
    find_edge.close_window(hwnd)
    find_edge.close_windows([hwnd1, hwnd2])

直接运行本文件：默认只列清单，不会关任何窗口。
    python find_edge.py                      只列出当前的 Edge 窗口
    python find_edge.py --close <hwnd> ...   关闭指定的 hwnd
"""
import sys

import edge_win
from advanced_print import print_pro

WIN32_OK = edge_win.WIN32_OK
WIN32_ERROR = edge_win.WIN32_ERROR


def find_edge_windows(title_contains=None, visible_only=True, skip_minimized=True):
    """列出符合条件的 Edge 顶层窗口 hwnd（只查询，无副作用）。

    参数:
        title_contains: 只保留标题里包含该子串的窗口；None 表示不按标题过滤
        visible_only:   True 只保留可见窗口（默认）；False 连隐藏的一起返回
                        （隐藏窗口不该被关，真要去关的时候别用 False）
        skip_minimized: True 跳过最小化的窗口（默认，与旧版行为一致）
    """
    return edge_win.list_windows(title_contains=title_contains,
                                 visible_only=visible_only,
                                 skip_minimized=skip_minimized)


def describe_window(hwnd):
    """窗口的一句话描述（state / title），用于打印；拿不到信息也不会抛异常。"""
    return edge_win.describe(hwnd)


def _to_int_list(value):
    """把入参转成 int 列表；转不了就抛 TypeError 并说清楚。"""
    if isinstance(value, bool):        # bool 是 int 的子类，这里必须挡掉
        raise TypeError("hwnds 不能是 bool：{!r}".format(value))
    if isinstance(value, int):
        return [value]
    if isinstance(value, str):         # 字符串是可迭代的，不挡掉会被逐字符遍历
        raise TypeError("hwnds 不能是字符串（{!r}）；需要 int 或 int 的列表".format(value))

    try:
        items = list(value)
    except TypeError:
        raise TypeError("hwnds 需要 int，或 int 的列表/元组/集合，收到：{!r}".format(value))

    result = []
    for item in items:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            raise TypeError("hwnds 里有不是整数的元素：{!r}".format(item))
    return result


def close_window(hwnd, skip_minimized=False):
    """关闭单个窗口（仅当它确实是活着的 Edge 窗口）。返回 True / False。"""
    if not WIN32_OK:
        print_pro("[错误] pywin32 不可用（{}），无法关闭窗口。".format(WIN32_ERROR), color="red")
        return False

    if not edge_win.is_edge_window(hwnd):
        print_pro("hwnd={} 不是活着的 Edge 窗口，未发送关闭消息。".format(hwnd), color="yellow")
        return False

    if skip_minimized and edge_win.is_minimized(hwnd):
        print_pro("hwnd={} 处于最小化状态，按 skip_minimized=True 跳过。".format(hwnd), color="yellow")
        return False

    if not edge_win.close(hwnd):
        print_pro("发送关闭消息失败 hwnd={}".format(hwnd), color="red")
        return False

    print_pro("已请求关闭 hwnd={}  {}".format(hwnd, edge_win.describe(hwnd)), color="green")
    return True


def close_windows(hwnds, skip_minimized=True):
    """关闭一批窗口，返回实际发出关闭消息的数量。

    hwnds 必须由调用方明确给出 —— 本模块不会再提供"帮我关掉所有 Edge 窗口"这类行为。
    """
    if not WIN32_OK:
        print("[错误] pywin32 不可用（{}），无法关闭窗口。".format(WIN32_ERROR))
        return 0

    targets = _to_int_list(hwnds)
    if not targets:
        print("没有给出要关闭的窗口，未做任何操作。")
        return 0

    print("要关闭的窗口：")
    checked = []
    for hwnd in targets:
        if not edge_win.is_edge_window(hwnd):
            print("  跳过 hwnd={}：不是活着的 Edge 窗口（可能已经关掉了）".format(hwnd))
            continue
        if skip_minimized and edge_win.is_minimized(hwnd):
            print("  跳过 hwnd={}：处于最小化状态（要关它请传 skip_minimized=False）".format(hwnd))
            continue
        print("  hwnd={}  {}".format(hwnd, edge_win.describe(hwnd)))
        checked.append(hwnd)

    if not checked:
        print("没有实际需要关闭的窗口，未发送任何关闭消息。")
        return 0

    sent = 0
    for hwnd in checked:
        if edge_win.close(hwnd):
            sent += 1
        else:
            print("  发送关闭消息失败 hwnd={}".format(hwnd))

    print("已向 {} 个窗口发送关闭消息".format(sent))
    print("注意：如果某个窗口开着多个标签页，Edge 可能弹“关闭全部标签页”的确认框。")
    return sent


def close_edge_windows(hwnds=None, skip_minimized=True):
    """旧名字，保留兼容。现在**必须显式给出 hwnd**。

    以前不带参数会把"所有可见的 Edge 窗口"一起关掉，那个行为已经删除 ——
    它会误关你自己开着的窗口。
    """
    if hwnds is None:
        print("[提示] close_edge_windows() 现在必须显式指定要关的窗口，例如：")
        print("        close_edge_windows([opener.hwnd])")
        print("        close_windows(find_edge_windows())")
        return 0

    if isinstance(hwnds, bool):        # 旧写法：close_edge_windows(False)
        print("[提示] 第一个参数现在要传 hwnd（或 hwnd 列表），bool 只当 skip_minimized 用。")
        return 0

    if hasattr(hwnds, "hwnd") or hasattr(hwnds, "hwnds"):
        print("[提示] 这里要传 hwnd 列表，不是 opener 对象。opener 请这样用：")
        print("        close_edge_windows([opener.hwnd])")
        return 0

    return close_windows(hwnds, skip_minimized=skip_minimized)


if __name__ == "__main__":
    args = sys.argv[1:]

    if args and args[0] == "--close":
        raw = args[1:]
        if not raw:
            print("用法：python find_edge.py --close <hwnd> [<hwnd> ...]")
            raise SystemExit(1)

        targets = []
        bad = []
        for text in raw:
            try:
                targets.append(int(text, 0))       # 允许 0x... 写法
            except ValueError:
                bad.append(text)
        if bad:
            print("这些参数不是合法的 hwnd，已中止，什么都没关：{}".format(", ".join(bad)))
            raise SystemExit(1)

        close_windows(targets, skip_minimized=False)
        raise SystemExit(0)

    # 默认：只列清单，不关任何窗口
    print("当前可见、未最小化的 Edge 窗口：")
    windows = find_edge_windows()
    if not windows:
        print("  （没有）")
    else:
        for hwnd in windows:
            print("  hwnd={}  {}".format(hwnd, describe_window(hwnd)))

    print()
    print("本文件默认只列出，不关闭任何窗口。要关某个窗口：")
    print("  python find_edge.py --close <hwnd> [<hwnd> ...]")
