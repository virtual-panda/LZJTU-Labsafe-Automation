"""链接表的读取、顺序游标 —— 完全不碰窗口，**也完全不写任何文件**。

链接顺序 = json 里 links 数组从上到下的顺序。

进度（游标）只是内存里的一个值，由调用方保管：

    cursor = LinkCursor("links.json")
    info = cursor.next()                 # 下一条
    state = cursor.state()               # 取出进度（dict，可直接 json.dumps）

    # ... 主程序把 state 存进自己的配置 / 数据库 / 内存 ...
    cursor = LinkCursor("links.json", state=state)    # 下次带着它续档

本模块**不读写任何进度文件** —— 打包成单文件 exe 时不需要落盘任何东西。
进度里存的是 last_url，还原时用 url 在链接表里定位，而不是用下标，
所以 links.json 中间插了或删了条目，进度也不会串位。
"""
import json
from typing import List, NamedTuple, Optional
from advanced_print import print_pro


class LinkInfo(NamedTuple):
    """一条链接的完整信息。

    用法（三种都行）：
        info.url / info.courseName / info.requiredStudyTime
        url, name, t = info          # 可以直接解包
        info._asdict()               # 转成 dict
    """
    url: str
    courseName: str
    requiredStudyTime: int

    def __str__(self):
        return self.url


def load_links(json_path: str = "links.json", encoding: str = "utf-8") -> List[LinkInfo]:
    """从 json 读取链接列表，返回 [LinkInfo, ...]（只读，不写任何东西）。

    json 形如：
        {"links": [{"courseName": "...", "url": "...", "requiredStudyTime": "300"}, ...]}
    也兼容顶层直接是数组的写法：[{...}, {...}]
    以 # 开头的 url 视为注释跳过；缺协议的自动补 https://
    """
    with open(json_path, "r", encoding=encoding) as fp:
        data = json.load(fp)

    if isinstance(data, dict):
        raw_links = data.get("links") or []
    elif isinstance(data, list):
        raw_links = data
    else:
        raise ValueError("{} 结构不对，应为对象(含 links)或数组".format(json_path))

    links = []
    for item in raw_links:
        if not isinstance(item, dict):
            continue

        url = str(item.get("url") or "").strip()
        if not url or url.startswith("#"):
            continue
        if not url.startswith(("http://", "https://", "file://")):
            url = "https://" + url

        course_name = str(item.get("courseName") or "")

        raw_time = item.get("requiredStudyTime")
        try:
            required_time = int(raw_time)          # "300" -> 300；300 -> 300
        except (TypeError, ValueError):
            required_time = 0                      # 空/非法值兜底

        links.append(LinkInfo(url, course_name, required_time))

    if not links:
        raise ValueError("{} 中没有读到任何链接".format(json_path))

    return links


class LinkCursor:
    """按 json 顺序推进的游标；进度不落盘，由调用方保管。

        cursor = LinkCursor("links.json")

        info = cursor.next()         # 下一条（推进进度）
        info = cursor.current()      # 重开"最近打开过的那条"（进度不动）
        cursor.position()            # 下一条是第几条（从 1 起），全部开完返回 None
        cursor.current_position()    # current() 会打开的是第几条
        cursor.remaining()           # 还剩几条
        cursor.total                 # 总条数
        cursor.reset()               # 回到第一条（只清内存里的游标）
        cursor.last() / cursor.all()
        cursor.state()               # 取出进度，交给调用方保存

    续档：把上次 cursor.state() 的返回值传回来即可

        cursor = LinkCursor("links.json", state=state)

    参数:
        json_path: json 文件路径（只读）
        encoding:  文件编码，常用 "utf-8"（带 BOM 可用 "utf-8-sig"）
        state:     上次保存的进度；None 表示从头开始
        verbose:   False 时不打印过程信息
    """

    def __init__(self, json_path: str = "links.json", encoding: str = "utf-8",
                 state=None, verbose: bool = True):
        self.json_path = json_path
        self.encoding = encoding
        self.verbose = verbose
        self.links = load_links(json_path, encoding=encoding)
        self.total = len(self.links)
        self._cursor = self._index_from_state(state)
        self._last = None
        self._last_index = None
        if self._cursor and self.verbose:
            print_pro("[续档] 上次打开到第 {} 条，本次从第 {} 条继续。".format(
                self._cursor, self._cursor + 1))

    # ---------- 内部 ----------

    def _index_from_state(self, state) -> int:
        """从进度数据里还原"下一条要打开的序号"；还原不了就返回 0。"""
        if not isinstance(state, dict):
            return 0

        last_url = state.get("last_url")
        if not last_url:
            return 0

        for index, item in enumerate(self.links):
            if item.url == last_url:
                return index + 1

        if self.verbose:
            print_pro("[提示] 传进来的进度里那条链接已不在链接表中，从第一条重新开始。", color="yellow")
        return 0

    def _visit(self, index: int) -> LinkInfo:
        """记录"这一条被打开了"（只在内存里）。"""
        info = self.links[index]
        self._last = info
        self._last_index = index
        return info

    # ---------- 对外 ----------

    def next(self) -> Optional[LinkInfo]:
        """下一条（推进进度）；全部开完返回 None。"""
        index = self._cursor
        if index >= self.total:
            return None
        self._cursor = index + 1
        return self._visit(index)

    def current(self) -> Optional[LinkInfo]:
        """重开当前这一条（最近打开过的那条），进度不动。还没打开过时就是第 1 条。"""
        index = self._cursor - 1 if self._cursor > 0 else 0
        return self._visit(index)

    def position(self) -> Optional[int]:
        """下一条的序号（从 1 起）；已经全部开完返回 None。"""
        if self._cursor >= self.total:
            return None
        return self._cursor + 1

    def current_position(self) -> int:
        """current() 会打开的那条的序号（从 1 起）。"""
        return (self._cursor - 1 if self._cursor > 0 else 0) + 1

    def remaining(self) -> int:
        """还剩几条没打开。"""
        return max(self.total - self._cursor, 0)

    def reset(self) -> None:
        """回到第一条（只清内存里的游标）。"""
        self._cursor = 0
        self._last = None
        self._last_index = None

    def last(self) -> Optional[LinkInfo]:
        """最近一次打开的 LinkInfo；没打开过则 None。"""
        return self._last

    def all(self) -> List[LinkInfo]:
        """全部链接（按 json 顺序）。"""
        return list(self.links)

    def state(self) -> dict:
        """取出当前进度，交给调用方保存（可直接 json.dumps）。

        还没打开过任何一条时返回的是一份"空进度"（字段都是 None），
        原样传回来就等价于从头开始。
        """
        return {
            "last_index": self._last_index,
            "last_url": self._last.url if self._last is not None else None,
            "last_course": self._last.courseName if self._last is not None else None,
        }
