import datetime


_COLORS = {
    "black": "\033[30m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
    "gray": "\033[90m",
    "grey": "\033[90m",
}
_RESET = "\033[0m"
_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def print_pro(content="", timestamp=False, color=None, end="\n"):
    """仅需一行代码，就能输出带有时间戳和颜色的内容。

    参数:
        content: 需要输出的内容。
        timestamp: 如果为 True，则在每一行输出前加上当前本地时间。默认false
        color: 颜色名称（例如 green或red）。
            None 表示不使用颜色。默认无颜色（None）。
        end: 输出后写入的文本，与 print 的行为一致。

    错误:
        ValueError: color 不在支持的颜色列表中。
        TypeError: 顾名思义，传错类型了。
    """
    if not isinstance(timestamp, bool):
        raise TypeError("timestamp must be a bool")
    if not isinstance(end, str):
        raise TypeError("end must be a string")

    if color is not None:
        if not isinstance(color, str):
            raise TypeError("color must be a string or None")
        color = color.lower()
        if color not in _COLORS:
            supported_colors = ", ".join(sorted(_COLORS))
            raise ValueError(
                f"unsupported color {color!r}; choose one of: {supported_colors}"
            )

    text = str(content)
    if timestamp:
        current_time = datetime.datetime.now().strftime(_TIMESTAMP_FORMAT)
        text = "\n".join(f"[{current_time}] {line}" for line in text.split("\n"))

    if color is not None:
        text = f"{_COLORS[color]}{text}{_RESET}"

    print(text, end=end)