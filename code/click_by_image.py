#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
click_by_image.py —— 在屏幕上按图片匹配定位，找到就点一次。

两种用法：

【一、当模块导入】最简调用只需传图片名和阈值：

    from click_by_image import click_image

    ok = click_image("play.png", confidence=0.9)
    if ok:
        print("点击成功")
    else:
        print("没找到")

    完整签名：
        click_image(image_name, confidence=0.9, timeout=5.0, interval=0.5,
                    region=None, scales=(1.0,), click_twice=False, dry_run=False,
                    verbose=False)

【二、当命令行用】

    python click_by_image.py 目标图.png
    python click_by_image.py 目标图.png --confidence 0.9 --timeout 30
    python click_by_image.py 目标图.png --region 0,0,1600,1200
    python click_by_image.py 目标图.png --scales 1.0,1.25,1.5 --dry-run

关于系统缩放（重要）：
    模板匹配是逐像素比对，要求目标图与屏幕上的图案尺寸完全一致。
    Windows 缩放不是 100% 时，屏幕上图案的像素尺寸会变（实测 150% 时相似度
    会从 1.0 崩到 0.33 左右，连 200% 这种整数倍也一样崩）。
    解决：用 scales 参数把模板按各缩放率重采样后再匹配，例如：
        click_image("play.png", scales=(1.0, 1.25, 1.5, 1.75, 2.0))
    最省事的做法是保持在目标缩放率下重新截图，此时 scales=(1.0,) 即可。
"""

import argparse
import os
import sys
import time
from advanced_print import print_pro

DEFAULT_CONFIDENCE = 0.9
DEFAULT_TIMEOUT = 5.0
DEFAULT_INTERVAL = 0.5


class MatchResult:
    """
    匹配结果。字段名与 PyAutoGUI 的 Box 一致（left/top/width/height），
    额外带 score（匹配分数 0~1）和 center（中心点）。
    """

    __slots__ = ("left", "top", "width", "height", "score")

    def __init__(self, left, top, width, height, score=0.0):
        self.left = int(left)
        self.top = int(top)
        self.width = int(width)
        self.height = int(height)
        self.score = float(score)

    @property
    def center(self):
        return (self.left + self.width // 2, self.top + self.height // 2)

    def __repr__(self):
        return (
            "MatchResult(left=%d, top=%d, width=%d, height=%d, score=%.4f)"
            % (self.left, self.top, self.width, self.height, self.score)
        )


# ======================================================================
# 核心函数：供外部 import 调用
# ======================================================================


def click_image(
    image_name,
    confidence=DEFAULT_CONFIDENCE,
    timeout=DEFAULT_TIMEOUT,
    interval=DEFAULT_INTERVAL,
    region=None,
    scales=(1.0,),
    click_twice=False,
    dry_run=False,
    verbose=False,
):
    """
    在屏幕上查找 image_name 指定的图案，找到后点击它（默认单击一次）。

    参数：
        image_name   目标图片的路径（建议用 png）。相对路径按当前工作目录解析。
        confidence   匹配相似度阈值，0~1。默认 0.9。越小越宽松，
                     找不到就往下调（如 0.8），误匹配就往上调（如 0.95）。
        timeout      最长等待秒数，默认 5。到期还没找到就放弃。
        interval     两次查找的间隔秒数，默认 0.5。
        region       只在屏幕的指定矩形内查找，格式 (left, top, width, height)。
                     传 None 表示全屏查找。
        scales       多尺度列表，默认 (1.0,)。系统缩放非 100% 时，
                     传入各候选缩放率，如 (1.0, 1.25, 1.5, 1.75, 2.0)。
        click_twice  True 则双击，默认单击。
        dry_run      True 则只查找不点击（用来验证匹配率）。
        verbose      True 则在控制台打印过程信息。

    返回：
        True  —— 找到并点击（或 dry_run 下找到）成功
        False —— 超时未找到

    异常：
        FileNotFoundError —— 图片不存在
        ValueError        —— 参数不合法（confidence 越界、scales 非法等）
        ImportError       —— 缺少 pyautogui / opencv-python 依赖
    """
    import pyautogui

    try:
        import cv2  # noqa: F401
    except ImportError:
        raise ImportError(
            "缺少 OpenCV，confidence 参数无法生效。请执行：pip install opencv-python"
        )

    if not os.path.isfile(image_name):
        raise FileNotFoundError("目标图不存在：" + str(image_name))

    if confidence <= 0 or confidence > 1:
        raise ValueError("confidence 必须在 (0, 1] 区间内，实际收到：" + str(confidence))

    if timeout <= 0:
        raise ValueError("timeout 必须大于 0，实际收到：" + str(timeout))

    if interval <= 0:
        raise ValueError("interval 必须大于 0，实际收到：" + str(interval))

    scale_list = _normalize_scales(scales)
    region_tuple = _normalize_region(region)

    if os.path.splitext(image_name)[1].lower() in (".jpg", ".jpeg"):
        if verbose:
            print_pro("[警告] 目标图是 JPEG，压缩噪点会降低匹配成功率，建议改用 PNG。", color="yellow")

    pyautogui.FAILSAFE = True  # 鼠标甩到屏幕左上角可紧急中止

    # 坐标系自检：size() 与截图尺寸不一致 = 点击必然偏移
    diag = diagnose_coordinates(pyautogui)
    if not diag["consistent"]:
        # 这是会导致"点偏"的严重问题，无论 verbose 与否都要警告
        print_pro("[警告] 坐标系不一致！pyautogui.size()="
            + str(diag["logical_size"])
            + " 但截图尺寸="
            + str(diag["physical_size"])
            + "，比率 "
            + str(diag["ratio"])
            + "。\n"
            "        匹配到的坐标会按此比率偏移，点击会点偏。\n"
            "        常见原因：显示缩放非 100%，而进程 DPI 感知为 UNAWARE。\n"
            "        解决：把系统缩放设为 100%，或改用 DPI 感知的 Python 启动方式。", color="red")

    if verbose:
        where = "全屏" if region_tuple is None else ("区域 " + str(region_tuple))
        print_pro("[信息] 目标图：" + image_name)
        print_pro("[信息] 查找范围：" + where + "，相似度阈值：" + str(confidence))
        print_pro("[信息] 尺度列表：" + ", ".join(str(s) for s in scale_list))
        print_pro("[信息] DPI 感知：" + diag["awareness"] + "，坐标系：" +
              ("一致" if diag["consistent"] else "不一致(比率 " + str(diag["ratio"]) + ")"))
        print_pro("[信息] 最长等待 "
            + str(timeout)
            + " 秒，每 "
            + str(interval)
            + " 秒查一次")

    # ---------- 轮询查找 ----------
    deadline = time.time() + timeout
    found = None

    while True:
        found = _find_on_screen(
            pyautogui, image_name, confidence, region_tuple, scale_list
        )
        if found is not None:
            break

        if time.time() >= deadline:
            break

        time.sleep(interval)

    if found is None:
        if verbose:
            print_pro("[结果] 超时，屏幕上没有找到匹配的图案。", color="yellow")
        return False

    center_x = int(found.left + found.width / 2)
    center_y = int(found.top + found.height / 2)

    match_score = getattr(found, "score", None)

    if verbose:
        score_text = "" if match_score is None else "，匹配分数 " + str(round(match_score, 4))
        print_pro("[结果] 找到目标：左上角 ("
            + str(found.left)
            + ", "
            + str(found.top)
            + ")，尺寸 "
            + str(found.width)
            + "x"
            + str(found.height)
            + "，中心点 ("
            + str(center_x)
            + ", "
            + str(center_y)
            + ")"
            + score_text)

    # 自检：匹配分数偏低说明可能找错了位置
    if match_score is not None and match_score < 0.95:
        print_pro("[警告] 匹配分数仅 "
            + str(round(match_score, 4))
            + "（建议 >0.95）。可能存在以下问题：\n"
            "        1. 屏幕上该图案的尺寸/外观与模板不完全一致；\n"
            "        2. 屏幕上有多个相似图案，当前命中的可能不是你要的那个；\n"
            "        3. confidence 设得过低，匹配到了背景杂点。\n"
            "        建议：用 find_candidates() 查看所有候选位置，或重新截取更精确的模板。", color="red")

    if match_score is not None and verbose:
        # 检测是否有多个强候选（容易点错）
        try:
            cands = find_candidates(
                image_name, confidence=match_score - 0.02, region=region_tuple, scales=scale_list
            )
            strong = [c for c in cands if c["score"] >= match_score - 0.02]
            if len(strong) > 1:
                print_pro("[警告] 屏幕上有 "
                    + str(len(strong))
                    + " 个位置匹配分数相近，点错风险高：", color="yellow")
                for c in strong[:5]:
                    print_pro("         位置 " + str(c["center"]) + " 分数 " + str(round(c["score"], 4)))
        except Exception:
            pass

    if dry_run:
        if verbose:
            print_pro("[结果] dry-run 模式，只查找不点击。")
        return True

    # ---------- 点击 ----------
    pyautogui.moveTo(center_x, center_y)
    time.sleep(0.05)

    if click_twice:
        pyautogui.doubleClick(center_x, center_y)
        if verbose:
            print_pro("[结果] 已双击。", color="green")
    else:
        pyautogui.click(center_x, center_y)
        if verbose:
            print_pro("[结果] 已单击。", color="green")

    return True


# ======================================================================
# 内部辅助函数
# ======================================================================


def diagnose_coordinates(pyautogui=None):
    """
    诊断坐标系是否一致——这是"点偏"类问题的根因检查。

    原理：PyAutoGUI 的 click 用逻辑坐标（GetSystemMetrics），
          而 locateOnScreen 的截图是物理像素。二者不一致时坐标会整体偏移。

    返回字典：
        consistent     True 表示坐标系一致，坐标可直接用于点击
        logical_size   pyautogui.size() 报的尺寸
        physical_size  实际截图尺寸
        ratio          物理/逻辑 的比率（1.0 表示一致）
        awareness      进程 DPI 感知状态的可读名称
        scale          由比率推算出的系统缩放百分比
    """
    if pyautogui is None:
        import pyautogui

    from PIL import ImageGrab

    logical = tuple(pyautogui.size())
    physical = tuple(ImageGrab.grab().size)

    ratio = physical[0] / logical[0] if logical[0] else 0.0
    consistent = abs(ratio - 1.0) < 1e-6

    # 读取进程 DPI 感知状态
    awareness_text = "未知"
    try:
        import ctypes

        value = ctypes.c_int()
        ctypes.windll.shcore.GetProcessDpiAwareness(None, ctypes.byref(value))
        awareness_map = {
            0: "UNAWARE（未感知，缩放非100%时会点偏）",
            1: "SYSTEM_DPI_AWARE（系统级）",
            2: "PER_MONITOR_DPI_AWARE（每显示器）",
        }
        awareness_text = awareness_map.get(value.value, str(value.value))
    except Exception:
        pass

    return {
        "consistent": consistent,
        "logical_size": logical,
        "physical_size": physical,
        "ratio": round(ratio, 4),
        "awareness": awareness_text,
        "scale": round(ratio * 100),
    }


def _normalize_scales(scales):
    if scales is None:
        return [1.0]

    # 允许传入单个数字，如 scales=1.5
    if isinstance(scales, (int, float)):
        scales = [scales]

    result = []
    for value in scales:
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError("scales 里每一项都必须是数字，实际收到：" + repr(value))
        if number <= 0:
            raise ValueError("scales 里的缩放率必须大于 0，实际收到：" + repr(value))
        result.append(number)

    if not result:
        raise ValueError("scales 不能为空")

    return result


def _normalize_region(region):
    """校验 region，返回 (left, top, width, height) 或 None。"""
    if region is None:
        return None

    if len(region) != 4:
        raise ValueError("region 必须是 (left, top, width, height) 四元组")

    left, top, width, height = region
    if width <= 0 or height <= 0:
        raise ValueError("region 的 width 和 height 必须大于 0")

    return (int(left), int(top), int(width), int(height))


def find_candidates(template_path, confidence=0.9, region=None, scales=(1.0,), max_results=20):
    """
    在屏幕上查找所有匹配位置，返回候选列表（按匹配分数从高到低）。

    这是排查"找错/点偏"的核心工具：如果屏幕上出现多个候选，说明模板
    特征不够独特，容易匹配到错误位置。

    返回列表，每项是字典：
        left, top, width, height  匹配区域
        center                    中心点 (x, y)
        score                     匹配分数 0~1
        scale                     命中时的缩放率
    """
    import cv2
    import numpy as np
    from PIL import Image

    import pyautogui

    scale_list = _normalize_scales(scales)
    region_tuple = _normalize_region(region)

    original = Image.open(template_path).convert("RGB")
    screen_img = pyautogui.screenshot(region=region_tuple)
    screen_np = cv2.cvtColor(np.array(screen_img), cv2.COLOR_RGB2BGR)

    candidates = []
    offset_left = region_tuple[0] if region_tuple else 0
    offset_top = region_tuple[1] if region_tuple else 0

    for scale in scale_list:
        tw = max(1, int(round(original.width * scale)))
        th = max(1, int(round(original.height * scale)))

        if tw > screen_np.shape[1] or th > screen_np.shape[0]:
            continue

        resized = original.resize((tw, th), Image.LANCZOS)
        tpl_np = cv2.cvtColor(np.array(resized), cv2.COLOR_RGB2BGR)

        result = cv2.matchTemplate(screen_np, tpl_np, cv2.TM_CCOEFF_NORMED)

        # 找出所有超过阈值的位置
        loc_r, loc_c = np.where(result >= confidence)
        for y, x in zip(loc_r, loc_c):
            score = float(result[y, x])
            left = int(x) + offset_left
            top = int(y) + offset_top
            # 去掉与已有候选重叠的（非极大值抑制的简化版）
            duplicate = False
            for existing in candidates:
                if (
                    abs(existing["left"] - left) < tw // 2
                    and abs(existing["top"] - top) < th // 2
                ):
                    duplicate = True
                    if score > existing["score"]:
                        existing.update(
                            {
                                "left": left,
                                "top": top,
                                "width": tw,
                                "height": th,
                                "center": (left + tw // 2, top + th // 2),
                                "score": score,
                                "scale": scale,
                            }
                        )
                    break
            if duplicate:
                continue

            candidates.append(
                {
                    "left": left,
                    "top": top,
                    "width": tw,
                    "height": th,
                    "center": (left + tw // 2, top + th // 2),
                    "score": score,
                    "scale": scale,
                }
            )

        # 只保留分数最高的前 N 个，避免列表爆炸
        candidates.sort(key=lambda c: -c["score"])
        candidates = candidates[:max_results]

    return candidates


def _find_on_screen(pyautogui, template_path, confidence, region, scales):
    """
    在屏幕（或指定区域）里找目标图，找不到返回 None。

    统一走 OpenCV 路径（不用 PyAutoGUI 原生 locateOnScreen），
    因为原生路径拿不到匹配分数，无法判断结果可信度。

    返回 MatchResult（兼容 PyAutoGUI 的 Box 接口，额外带 score 字段）。
    """
    import cv2
    import numpy as np
    from PIL import Image

    original = Image.open(template_path).convert("RGB")
    screen_img = pyautogui.screenshot(region=region)
    screen_np = cv2.cvtColor(np.array(screen_img), cv2.COLOR_RGB2BGR)

    best_value = -1.0
    best_loc = None
    best_size = None

    for scale in scales:
        tw = max(1, int(round(original.width * scale)))
        th = max(1, int(round(original.height * scale)))

        if tw > screen_np.shape[1] or th > screen_np.shape[0]:
            continue  # 这个尺度下模板比屏幕还大，跳过

        resized = original.resize((tw, th), Image.LANCZOS)
        tpl_np = cv2.cvtColor(np.array(resized), cv2.COLOR_RGB2BGR)

        result = cv2.matchTemplate(screen_np, tpl_np, cv2.TM_CCOEFF_NORMED)
        _, max_value, _, max_loc = cv2.minMaxLoc(result)

        if max_value > best_value:
            best_value = max_value
            best_loc = max_loc
            best_size = (tw, th)

    if best_loc is None or best_value < confidence:
        return None

    offset_left = region[0] if region else 0
    offset_top = region[1] if region else 0
    left = best_loc[0] + offset_left
    top = best_loc[1] + offset_top

    return MatchResult(left, top, best_size[0], best_size[1], best_value)


# ======================================================================
# 命令行外壳
# ======================================================================


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="在屏幕上查找指定图片，找到后单击一次。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("template", help="要匹配的目标小图路径（建议 png）")
    parser.add_argument(
        "--confidence",
        type=float,
        default=DEFAULT_CONFIDENCE,
        help="匹配相似度阈值 0~1，默认 0.9（越小越宽松）",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="最长等待秒数，默认 5",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL,
        help="每次查找的间隔秒数，默认 0.5",
    )
    parser.add_argument(
        "--region",
        default=None,
        help='只在指定区域查找，格式 "left,top,width,height"',
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只查找不点击，打印结果",
    )
    parser.add_argument(
        "--click-twice",
        action="store_true",
        help="双击而不是单击",
    )
    parser.add_argument(
        "--scales",
        default="1.0",
        help='多尺度搜索，逗号分隔，例如 "1.0,1.25,1.5"。默认只搜 1.0',
    )
    return parser.parse_args(argv)


def parse_region_arg(region_str):
    """把命令行里的 "left,top,width,height" 解析成四元组。"""
    if region_str is None:
        return None

    parts = region_str.split(",")
    if len(parts) != 4:
        raise ValueError(
            'region 格式错误，应为 "left,top,width,height"，例如 "0,0,1600,1200"'
        )

    numbers = []
    for piece in parts:
        try:
            numbers.append(int(piece.strip()))
        except ValueError:
            raise ValueError("region 里每一项都必须是整数，实际收到：" + piece.strip())

    return _normalize_region(tuple(numbers))


def parse_scales_arg(scales_str):
    """把命令行里的 "1.0,1.25,1.5" 解析成浮点数列表。"""
    return _normalize_scales(scales_str.split(","))


def main(argv):
    args = parse_args(argv)

    # ---------- 依赖检查 ----------
    try:
        import pyautogui  # noqa: F401
    except ImportError:
        print("[错误] 没有安装 PyAutoGUI。请执行：pip install pyautogui", file=sys.stderr)
        return 2

    try:
        import cv2  # noqa: F401
    except ImportError:
        print(
            "[错误] 缺少 OpenCV，--confidence 无法生效。\n"
            "       请执行：pip install opencv-python",
            file=sys.stderr,
        )
        return 2

    if not os.path.isfile(args.template):
        print("[错误] 目标图不存在：" + args.template, file=sys.stderr)
        return 2

    # ---------- 参数解析 ----------
    try:
        region = parse_region_arg(args.region)
    except ValueError as exc:
        print("[错误] " + str(exc), file=sys.stderr)
        return 2

    try:
        scales = parse_scales_arg(args.scales)
    except ValueError as exc:
        print("[错误] " + str(exc), file=sys.stderr)
        return 2

    # ---------- 调用核心函数 ----------
    try:
        ok = click_image(
            args.template,
            confidence=args.confidence,
            timeout=args.timeout,
            interval=args.interval,
            region=region,
            scales=scales,
            click_twice=args.click_twice,
            dry_run=args.dry_run,
            verbose=True,
        )
    except ValueError as exc:
        print("[错误] " + str(exc), file=sys.stderr)
        return 2

    if not ok:
        print("[结果] 超时，屏幕上没有找到匹配的图案。", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
