"""按序打开链接的薄壳：只负责把三个黑盒拼起来。

真正的逻辑都在别的模块里：
    link_cursor.py  链接表顺序 + 游标（不碰窗口，也不写任何文件）
    edge_open.py    启动 Edge 并强制最大化（只依赖 edge_win）
    edge_win.py     Win32 窗口原语（全项目唯一 import pywin32 的地方）

**本程序不落盘任何文件**：游标只是一个值，由调用方保存和回传。
打包成单文件 exe 时不需要写任何东西到磁盘。

本文件是一组"拼装示例"，供不想自己拼的业务直接调用。
想自己拼的话，照抄下面 open_next 里那几行即可：

    cursor = LinkCursor("links.json", state=state)   # state 由你自己保管
    info = cursor.next()                             # 或 cursor.current()
    hwnd = open_url(info.url)                         # 新开窗口并最大化
    state = cursor.state()                            # 存起来，下次传回来
    close_window(hwnd)                                # 只关自己开的那个

命令行：
    python read_and_open_link.py                              交互式：一条一条往下开
    python read_and_open_link.py next [--state '<json>']      只开下一条，并把新状态打印出来
    python read_and_open_link.py current [--state '<json>']   重开当前这条，并打印状态

    （没有落盘就没有"自动续档"：把打印出来的状态用 --state 传回来，才是续档。）
"""
import json
import sys

from edge_open import open_url
# LinkInfo / load_links 一并再导出，保持旧的引用路径可用
from link_cursor import LinkInfo, LinkCursor, load_links
from advanced_print import print_pro


def make_link_opener(json_path="links.json", new_window=True, encoding="utf-8",
                     open_timeout=15.0, verbose=True, state=None):
    """旧的对外接口，保持不变：返回一个 opener 函数（另外挂了几个属性）。

    链接顺序 = json 里 links 数组从上到下的顺序。

    opener(mode)：
        opener("next")    （等价于 opener()）打开"下一条"，进度往后推一位
        opener("current") 重新打开"当前这一条"（最近打开过的那条），进度不动；
                          还没打开过任何一条时，current 就是第 1 条
        全部打开完后返回 None

    返回值 LinkInfo：.url / .courseName / .requiredStudyTime，str() 出来就是 url。

    opener 上的属性：
        opener.state()         -> dict          取出进度，交给调用方保存
        opener.hwnd            -> int 或 None   最近一次打开成功后拿到的窗口 hwnd
        opener.hwnds()         -> [int, ...]    本 opener 打开成功过的所有窗口 hwnd
        opener.position(mode)  -> int 或 None   即将打开的是第几条（从 1 起）
        opener.remaining()     -> int           还剩几条没打开
        opener.total           -> int           总条数
        opener.reset()         -> None          回到第一条（只清内存里的游标）
        opener.last()          -> LinkInfo 或 None
        opener.all()           -> [LinkInfo, ...]

    续档（本程序不落盘，状态由你保管）：
        state = opener.state()                       # 存进你自己的配置/数据库
        opener = make_link_opener(state=state)       # 下次带着它接着来

    参数:
        json_path / encoding / verbose / state : 透传给 LinkCursor
        state:     上次 opener.state() 的返回值；None 表示从头开始
        new_window: True  -> 每条都开新窗口（默认），并强制最大化
                    False -> 在当前窗口开新标签页（不开新窗口，也就没有 hwnd）
        open_timeout: 等新窗口出现的最长秒数；超时只打印告警，不影响链接被打开
    """
    cursor = LinkCursor(json_path, encoding=encoding, state=state, verbose=verbose)
    opened = []

    def open_next(mode="next"):
        """按 mode 打开一条链接，返回 LinkInfo；没有可打开的就返回 None。"""
        if mode == "current":
            position = cursor.current_position()
            info = cursor.current()
        elif mode == "next":
            position = cursor.position()
            info = cursor.next()
        else:
            raise ValueError("mode 只支持 'next' 或 'current'，收到：{!r}".format(mode))

        if info is None:
            return None

        # 先清成 None：这次要是没拿到窗口，属性就如实反映"没有"
        open_next.hwnd = open_url(info.url, new_window=new_window,
                                  timeout=open_timeout, verbose=verbose)
        if open_next.hwnd is not None:
            opened.append(open_next.hwnd)

        if verbose:
            print_pro("[{}/{}] 已打开({}): {}  ({})".format(
                position, cursor.total, mode, info.url, info.courseName), color="green")
        return info

    def position(mode="next"):
        """即将打开的链接序号（从 1 起）；next 模式下已经全部打开完则返回 None。"""
        if mode == "current":
            return cursor.current_position()
        return cursor.position()

    open_next.hwnd = None
    open_next.hwnds = lambda: list(opened)
    open_next.state = cursor.state
    open_next.position = position
    open_next.remaining = cursor.remaining
    open_next.total = cursor.total
    open_next.reset = cursor.reset
    open_next.last = cursor.last
    open_next.all = cursor.all
    return open_next


def _print_link(info, opener, position=None):
    """打印一条链接的信息。"""
    print(f"课程：{info.courseName}")
    print(f"链接：{info.url}")
    print(f"要求学习时长：{info.requiredStudyTime}")
    print(f"窗口 hwnd：{opener.hwnd}")
    if position is not None:
        print(f"进度：第 {position} / {opener.total} 条")


def _parse_args(argv):
    """解析命令行：返回 (mode, state)。"""
    mode = None
    state = None
    rest = list(argv)

    if rest and not rest[0].startswith("-"):
        mode = rest.pop(0).lower()
        if mode not in ("next", "current"):
            print("用法：python read_and_open_link.py [next|current] [--state '<json>']")
            raise SystemExit(1)

    while rest:
        item = rest.pop(0)
        if item == "--state" and rest:
            text = rest.pop(0)
        elif item.startswith("--state="):
            text = item.split("=", 1)[1]
        else:
            print("不认识的参数：{}".format(item))
            raise SystemExit(1)

        try:
            state = json.loads(text)
        except ValueError as exc:
            print("--state 不是合法 JSON：{}".format(exc))
            raise SystemExit(1)

    return mode, state


if __name__ == "__main__":
    mode, state = _parse_args(sys.argv[1:])
    opener = make_link_opener("links.json", new_window=True, state=state)

    if mode is not None:
        # 单次模式：开一条就退出，把新状态打印出来交给调用方保存
        position = opener.position(mode)
        info = opener(mode)
        if info is None:
            print("已经到最后一条了，没有下一条可开。")
            print("要重新开始：传空的 state（不传 --state）即可。")
            raise SystemExit(0)
        _print_link(info, opener, position)
        print("state（请自己保存，下次用 --state 传回来续档）：")
        print(json.dumps(opener.state(), ensure_ascii=False))
        raise SystemExit(0)

    # ---------- 交互模式 ----------
    while True:
        position = opener.position()
        info = opener()
        if info is None:
            print("已全部打开完毕")
            print("当前 state：")
            print(json.dumps(opener.state(), ensure_ascii=False))
            print("要从头再来一遍：调用 opener.reset()，或下次不传 state")
            break

        _print_link(info, opener, position)
        input("按回车继续打开下一条...")
