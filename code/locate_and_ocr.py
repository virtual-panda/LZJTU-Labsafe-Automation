# -*- coding: utf-8 -*-
"""
UI 元素定位 + OCR 尝试性程序
============================

整个流程分成四步，每一步都是一个独立的函数，方便单独调试：

    1. 截屏            grab_screen_bgr()
    2. 模板匹配定位     match_multiscale()      —— 找 template.png 在屏幕上的位置
    3. 裁剪 + 预处理    crop_region() / build_ocr_variants()
    4. OCR 识别        run_ocr()               —— RapidOCR(ONNX)，中英文都认

用法示例：
    python locate_and_ocr.py                    # 定位 + OCR，打印结果
    python locate_and_ocr.py --debug            # 额外保存标注图到 debug/
    python locate_and_ocr.py --top 3            # 找前 3 个候选位置
    python locate_and_ocr.py --image shot.png   # 不截屏，拿一张已有图片当"屏幕"（离线调试用）
    python locate_and_ocr.py --watch            # 每 2 秒重复一次，Ctrl+C 退出
    python locate_and_ocr.py --info             # 只打印屏幕 / 缩放信息，不干活

依赖（都已装好）：
    pyautogui  pillow  opencv-python  numpy  rapidocr  onnxruntime
"""

import argparse
import difflib
import re
import sys
import time
from collections import namedtuple
from pathlib import Path

import cv2
import numpy as np
import pyautogui
from PIL import Image
from advanced_print import print_pro

# Windows 控制台默认可能是 GBK，直接切 UTF-8，免得打印中文时炸掉
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_TEMPLATE = PROJECT_DIR / "template.png"
DEBUG_DIR = PROJECT_DIR / "debug"

# 匹配得分低于这个值就认为"没找到"，避免把错误位置当成结果报出来
DEFAULT_THRESHOLD = 0.70
# OCR 前把区域放大多少倍（小字直接喂给 OCR 效果差，放大 3 倍最稳）
DEFAULT_UPSCALE = 3.0
# "07:40" / "7：40" / "103:07" 这类时间格式
TIME_PATTERN = re.compile(r"^\s*(\d{1,3})\s*[:：]\s*(\d{1,2})\s*$")
TIME_SEARCH_PATTERN = re.compile(r"\d{1,3}\s*[:：]\s*\d{1,2}")


# ===========================================================================
# 第 0 部分：小工具
# ===========================================================================

def log(message=""):
    """带 flush 的打印，保证在 --watch 模式下也能实时看到输出。"""
    print_pro(message)
    sys.stdout.flush()


def load_image_bgr(path):
    """读一张图，统一返回 3 通道 BGR 的 numpy 数组。

    模板图是 RGBA 的。如果 alpha 通道全是不透明的（截图裁出来基本都是），
    直接丢掉 alpha；万一真有透明像素，就合成到白底上，免得后面算出黑边。
    """
    img = Image.open(path)

    if img.mode == "RGBA":
        alpha = np.array(img.getchannel("A"))
        if alpha.min() < 255:
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.getchannel("A"))
            rgb = np.array(background)
        else:
            rgb = np.array(img.convert("RGB"))
    else:
        rgb = np.array(img.convert("RGB"))

    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    return bgr


def open_mss():
    """打开一个 mss 截图会话。

    mss 10.x 起把入口从 mss.mss() 改成了 mss.MSS()，老版本没有 MSS。
    这里做一下兼容，免得依赖版本一变就报 DeprecationWarning 或 AttributeError。
    """
    import mss

    if hasattr(mss, "MSS"):
        return mss.MSS()
    return mss.mss()


def grab_screen_bgr(use_mss=True, monitor_index=1):
    """截取屏幕，返回 BGR 数组。

    默认走 mss（快，一次大约 10~20ms），mss 不可用时退回 pyautogui。
    返回的是**物理像素**尺寸的图，可能比 pyautogui.size() 大（见 get_coord_scale）。

    monitor_index 是 mss 的显示器编号：
        0 = 所有显示器拼成的虚拟桌面
        1 = 主显示器
        2、3…… = 其他显示器
    默认只截**主显示器**，因为 pyautogui 的坐标就是主显示器的坐标系，
    两者范围一致才不会算错坐标。多显示器用户如果目标在副屏上，先用 --info
    看清尺寸再决定要不要调 --monitor。
    """
    if use_mss:
        try:
            with open_mss() as sct:
                if monitor_index >= len(sct.monitors):
                    log("[提示] 显示器编号 %d 不存在（本机共 %d 个），回退到主显示器。"
                        % (monitor_index, len(sct.monitors) - 1))
                    monitor_index = 1
                monitor = sct.monitors[monitor_index]
                shot = np.array(sct.grab(monitor))
            # mss 返回的是 BGRA，去掉 alpha
            bgr = cv2.cvtColor(shot, cv2.COLOR_BGRA2BGR)
            return bgr
        except Exception as error:
            log("[提示] mss 截屏失败（%s），改用 pyautogui。" % error)

    pil_image = pyautogui.screenshot()
    rgb = np.array(pil_image)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    return bgr


def get_coord_scale(image_width, image_height):
    """算「截图坐标 -> 鼠标坐标」的换算比例。

    这是 Windows 上最容易踩的坑：
      - 截图拿到的是**物理像素**（比如 2560x1440）
      - pyautogui.size() / moveTo() 用的是**逻辑像素**（比如 1707x960，系统缩放 150%）
    两者不一致时，直接把截图里的坐标丢给 moveTo，鼠标会跑偏。

    返回 (scale_x, scale_y)，把截图坐标乘上它就得到鼠标坐标。
    """
    logical_width, logical_height = pyautogui.size()
    scale_x = logical_width / image_width
    scale_y = logical_height / image_height
    return scale_x, scale_y


# ===========================================================================
# 第 1 部分：模板预处理
# ===========================================================================

def find_content_box(template_bgr, tolerance=10):
    """找出模板里"有内容"的那块矩形（裁掉四周大片纯色背景）。

    为什么要这一步：这张模板 140x276，其中 86% 的像素是同一个背景色。
    背景不携带任何信息，却会稀释匹配得分。裁到文字外框再匹配，峰值更尖锐、
    也更容易区分"真找到"和"碰巧有点像"。

    返回 (x, y, w, h)，已经是裁剪用的坐标。
    """
    height, width = template_bgr.shape[:2]

    # 用最外圈 2 像素估计背景色（取中位数，避免少量杂点干扰）
    frame_parts = [
        template_bgr[0:2, :, :].reshape(-1, 3),
        template_bgr[height - 2:height, :, :].reshape(-1, 3),
        template_bgr[:, 0:2, :].reshape(-1, 3),
        template_bgr[:, width - 2:width, :].reshape(-1, 3),
    ]
    frame_pixels = np.concatenate(frame_parts, axis=0)
    background = np.median(frame_pixels, axis=0)

    # 每个像素和背景色比，任一通道差得够多就算"内容"
    difference = np.abs(template_bgr.astype(np.int16) - background.astype(np.int16))
    content_mask = difference.max(axis=2) > tolerance

    rows = np.where(content_mask.any(axis=1))[0]
    columns = np.where(content_mask.any(axis=0))[0]

    if len(rows) == 0 or len(columns) == 0:
        # 整张图都是纯色，没什么可裁的
        return 0, 0, width, height

    x0 = int(columns[0])
    y0 = int(rows[0])
    x1 = int(columns[-1]) + 1
    y1 = int(rows[-1]) + 1
    return x0, y0, x1 - x0, y1 - y0


def to_match_space(image_bgr, mode):
    """把图片转成"用来匹配"的表示形式。

    gray  —— 转灰度。默认，够用且最快。
    edge  —— 先转灰度再提 Canny 边缘。只保留轮廓，对界面换配色（浅色/深色主题）
             的适应性更强，代价是信息量少一些。
    color —— 直接用三通道原图匹配。颜色本身就是特征时用（比如"红色数字"
             这种靠颜色区分的目标）。
    """
    if mode == "gray":
        return cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    if mode == "edge":
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        edges = cv2.Canny(blurred, 50, 150)
        return edges

    if mode == "color":
        return image_bgr

    raise ValueError("未知的匹配模式: %s" % mode)


# ===========================================================================
# 第 2 部分：模板匹配定位
# ===========================================================================

def build_scale_list(low, high, step):
    """生成一串缩放比例，例如 0.5 0.55 0.6 ... 2.0。"""
    scales = []
    value = low
    # 用 1e-9 的容差处理浮点累加误差，免得 2.0 被漏掉
    while value <= high + 1e-9:
        scales.append(round(value, 4))
        value += step
    return scales


def match_at_scale(screen_m, template_m, scale, method=cv2.TM_CCOEFF_NORMED):
    """在**某一个**缩放比例下跑一次 matchTemplate。

    返回 (score, x, y, width, height)，全部是传进来的图（screen_m）的像素坐标。
    模板比屏幕还大（这个缩放比例不合理）时返回 None。
    """
    if abs(scale - 1.0) < 1e-6:
        template_scaled = template_m
    else:
        # 缩小用 INTER_AREA（抗锯齿更好），放大用 INTER_CUBIC
        if scale < 1.0:
            interpolation = cv2.INTER_AREA
        else:
            interpolation = cv2.INTER_CUBIC
        template_scaled = cv2.resize(
            template_m, None, fx=scale, fy=scale, interpolation=interpolation
        )

    template_height, template_width = template_scaled.shape[:2]
    screen_height, screen_width = screen_m.shape[:2]

    # 缩得太小（几个像素）就没有匹配的意义了，直接跳过
    if template_height < 3 or template_width < 3:
        return None
    if template_height > screen_height or template_width > screen_width:
        return None

    result = cv2.matchTemplate(screen_m, template_scaled, method)
    min_value, max_value, min_location, max_location = cv2.minMaxLoc(result)

    x, y = max_location
    return float(max_value), int(x), int(y), int(template_width), int(template_height)


def _refine_locally(screen_m, template_m, method, coarse_best, low, high,
                    coarse_step, fine_step):
    """在粗扫结果附近开一个小窗口，用全分辨率把位置和倍率重新算准。

    为什么要开窗口而不是再全屏扫一遍：粗扫已经把位置锁定到一个点了，
    全屏重扫纯属浪费。实测全屏单次匹配 95ms，局部窗口只要不到 2ms。

    返回结果字典（含 score / x / y / width / height / scale）。
    """
    screen_height, screen_width = screen_m.shape[:2]

    # 窗口要留够余量：粗扫可能降过采样，位置有几个像素偏差；
    # 倍率差一点，模板尺寸也会差几个像素。取模板长边的 12%，至少 24 像素。
    margin = max(24, int(0.12 * max(coarse_best["width"], coarse_best["height"])))

    x0 = max(0, coarse_best["x"] - margin)
    y0 = max(0, coarse_best["y"] - margin)
    x1 = min(screen_width, coarse_best["x"] + coarse_best["width"] + margin)
    y1 = min(screen_height, coarse_best["y"] + coarse_best["height"] + margin)

    window = screen_m[y0:y1, x0:x1]

    # 精扫的倍率范围：粗扫倍率 ± 一个粗扫步长
    fine_low = max(low, coarse_best["scale"] - coarse_step)
    fine_high = min(high, coarse_best["scale"] + coarse_step)

    # 粗扫那个倍率也要在全分辨率下重算一次 —— 不能直接把降采样得到的分数
    # 当成最终分数报出去，那样分数会偏乐观。
    candidate_scales = set(build_scale_list(fine_low, fine_high, fine_step))
    candidate_scales.add(coarse_best["scale"])

    best = None
    for scale in sorted(candidate_scales):
        result = match_at_scale(window, template_m, scale, method)
        if result is None:
            continue

        score, x, y, width, height = result

        if best is None or score > best["score"]:
            best = {
                "score": score,
                "x": x + x0,          # 换算回全屏坐标
                "y": y + y0,
                "width": width,
                "height": height,
                "scale": scale,
            }

    if best is None:
        # 极小概率：窗口小到放不下模板。退回粗扫结果，
        # 但这时候分数是降采样算的，会比真实值略低，属于保守方向，可以接受。
        return {
            "score": coarse_best["coarse_score"],
            "x": coarse_best["x"],
            "y": coarse_best["y"],
            "width": coarse_best["width"],
            "height": coarse_best["height"],
            "scale": coarse_best["scale"],
        }

    return best


def match_multiscale(screen_m, template_m, method_name="ccoef",
                     low=0.5, high=2.0, coarse_step=0.05, fine_step=0.01,
                     coarse_downscale=2):
    """多尺度模板匹配：粗扫定大概位置和倍率，再在附近全分辨率精修。

    **为什么要多尺度**：模板是从某次截图裁出来的，实际运行时的系统缩放
    （100% / 125% / 150%）或界面自身的缩放可能不同，模板必须跟着缩放才能对上。

    **为什么要分两级**：0.5~2.0 按 0.01 一步是 151 次匹配，太慢；
    先用 0.05 粗扫找到大致倍率，再在附近用 0.01 精修，几十次就能达到同样精度。

    **为什么要降采样（coarse_downscale）**：实测在 3200x2000 的屏幕上，
    全分辨率粗扫 31 次要 2.95 秒（单次 95ms）；把屏幕缩到一半再扫只要 0.64 秒
    （单次 21ms），快 4.6 倍。粗扫只负责回答"大概在哪、大概多大"，
    2 个像素的定位误差完全够用 —— 位置和倍率最终由精修在全分辨率下重新算准。

    coarse_downscale=1 表示不降采样（最准但最慢），适合出问题时对照排查。

    返回 (最佳结果字典 或 None, 说明文字列表)
    """
    if method_name == "ccorr":
        method = cv2.TM_CCORR_NORMED
    else:
        method = cv2.TM_CCOEFF_NORMED

    notes = []

    # ---------- 第一级：粗扫 ----------
    if coarse_downscale > 1:
        coarse_screen = cv2.resize(
            screen_m, None,
            fx=1.0 / coarse_downscale, fy=1.0 / coarse_downscale,
            interpolation=cv2.INTER_AREA,
        )
    else:
        coarse_screen = screen_m

    coarse_best = None
    for scale in build_scale_list(low, high, coarse_step):
        # 屏幕缩了 N 倍，模板也要跟着缩 N 倍，"匹配尺度"才和原来一致
        result = match_at_scale(coarse_screen, template_m,
                                scale / coarse_downscale, method)
        if result is None:
            continue

        score, x, y, width, height = result

        if coarse_best is None or score > coarse_best["coarse_score"]:
            coarse_best = {
                "coarse_score": score,
                # 坐标换算回全分辨率的尺度
                "x": int(round(x * coarse_downscale)),
                "y": int(round(y * coarse_downscale)),
                "width": int(round(width * coarse_downscale)),
                "height": int(round(height * coarse_downscale)),
                "scale": scale,
            }

    if coarse_best is None:
        return None, notes

    notes.append(
        "粗扫：scale=%.2f  位置=(%d, %d)  粗扫得分=%.4f  (屏幕缩到 1/%d)"
        % (coarse_best["scale"], coarse_best["x"], coarse_best["y"],
           coarse_best["coarse_score"], coarse_downscale)
    )

    # ---------- 第二级：局部精修 ----------
    best = _refine_locally(screen_m, template_m, method, coarse_best,
                           low, high, coarse_step, fine_step)

    notes.append(
        "精修：scale=%.2f  位置=(%d, %d)  得分=%.4f  (全分辨率，局部窗口)"
        % (best["scale"], best["x"], best["y"], best["score"])
    )

    return best, notes


def find_top_matches(score_map, template_width, template_height,
                     threshold, top_n, overlap_limit=0.3):
    """从得分图里挑出若干个互不重叠的位置（简单版 NMS 非极大值抑制）。

    用途：同一个模板在屏幕上可能出现多次，比如列表里每一行都有类似的
    "已学习 / 要求学习" 卡片，这时候需要把前几个位置都找出来。

    返回 [(x, y, score), ...]，按得分从高到低。
    """
    ys, xs = np.where(score_map >= threshold)
    if len(xs) == 0:
        return []

    scores = score_map[ys, xs]
    order = np.argsort(-scores)

    picked = []
    for index in order:
        x = int(xs[index])
        y = int(ys[index])
        score = float(scores[index])

        keep = True
        for existing_x, existing_y, _ in picked:
            # 两个框的重叠面积 / 并集面积（IoU）
            inter_x0 = max(x, existing_x)
            inter_y0 = max(y, existing_y)
            inter_x1 = min(x + template_width, existing_x + template_width)
            inter_y1 = min(y + template_height, existing_y + template_height)
            inter_width = max(0, inter_x1 - inter_x0)
            inter_height = max(0, inter_y1 - inter_y0)
            intersection = inter_width * inter_height
            union = template_width * template_height * 2 - intersection
            if union > 0 and intersection / union > overlap_limit:
                keep = False
                break

        if keep:
            picked.append((x, y, score))
        if len(picked) >= top_n:
            break

    return picked


# ===========================================================================
# 第 3 部分：OCR
# ===========================================================================

class OcrEngine:
    """RapidOCR 的懒加载包装。

    构造 RapidOCR 会加载 3 个 onnx 模型（检测 + 方向分类 + 识别），要一两秒。
    所以第一次真正用到时才构造，之后复用。
    """

    def __init__(self):
        self._engine = None

    def get(self):
        if self._engine is None:
            from rapidocr import RapidOCR

            # 把 rapidocr 自己的 INFO 日志压到 error，否则输出太吵
            self._engine = RapidOCR(params={"Global.log_level": "error"})
        return self._engine


def crop_region(image_bgr, x, y, width, height, padding=4):
    """按矩形裁剪，并留一点外扩边距。

    留边距是因为：匹配框可能刚好贴着文字边缘，裁得严丝合缝会把笔画切掉，
    OCR 就容易读错。外扩几个像素给检测模型一点呼吸空间。

    返回 (裁剪出的图, 实际使用的外扩量 dict)。超出图片边界时自动收窄。
    """
    image_height, image_width = image_bgr.shape[:2]

    x0 = max(0, int(x) - padding)
    y0 = max(0, int(y) - padding)
    x1 = min(image_width, int(x) + int(width) + padding)
    y1 = min(image_height, int(y) + int(height) + padding)

    crop = image_bgr[y0:y1, x0:x1]
    box = {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}
    return crop, box


def build_ocr_variants(crop_bgr, upscale):
    """为 OCR 准备几个预处理版本。

    OCR 对小字天生不友好，所以：
      1. 先放大（默认 3 倍），笔画变粗，检测模型更容易框住
      2. 再多给一个"灰度高对比"版本 —— 这张图里 "已学习 / 要求学习" 是浅灰字，
         和米色背景对比度很低，普通版本可能漏检，CLAHE 拉一把对比度就出来了

    返回 [(名称, BGR 图像), ...]
    """
    variants = []

    big = cv2.resize(
        crop_bgr, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC
    )
    variants.append(("原始放大", big))

    gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray_enhanced = clahe.apply(gray)
    variants.append(("灰度增强", cv2.cvtColor(gray_enhanced, cv2.COLOR_GRAY2BGR)))

    return variants


def parse_ocr_output(result, upscale, crop_box):
    """把 RapidOCR 的返回整理成统一结构的列表。

    RapidOCR 返回的是 RapidOCROutput，字段：
        boxes  —— (N, 4, 2) float32，每个文本框的四个角点
        txts   —— 识别出的文字
        scores —— 每行的置信度

    这里要把坐标从「放大后的裁剪图」换算回「原始屏幕坐标」，否则画框会错位。

    返回 [{"text":..., "score":..., "box":((x0,y0),(x1,y1)), "center":(cx,cy)}, ...]
    """
    if result is None:
        return []

    boxes = getattr(result, "boxes", None)
    texts = getattr(result, "txts", None)
    scores = getattr(result, "scores", None)

    if boxes is None or texts is None:
        return []

    items = []
    for index in range(len(texts)):
        corners = boxes[index]

        # 坐标先除以放大倍数回到裁剪图坐标，再加上裁剪图在屏幕上的左上角
        xs = corners[:, 0] / upscale + crop_box["x"]
        ys = corners[:, 1] / upscale + crop_box["y"]

        x0 = float(np.min(xs))
        y0 = float(np.min(ys))
        x1 = float(np.max(xs))
        y1 = float(np.max(ys))

        if scores is None:
            score = 0.0
        else:
            score = float(scores[index])

        text = str(texts[index])

        items.append({
            "text": text,
            "score": score,
            "box": ((x0, y0), (x1, y1)),
            "center": ((x0 + x1) / 2.0, (y0 + y1) / 2.0),
        })

    # 按从上到下、从左到右排序，方便后面配对
    items.sort(key=lambda item: (round(item["center"][1] / 8), item["center"][0]))
    return items


def run_ocr(crop_bgr, crop_box, upscale, verbose=False):
    """对一个裁剪区域跑 OCR，返回识别结果列表 + 说明文字。

    会依次跑所有预处理版本，取「行数 x 平均置信度」最高的那个作为结果。
    这样浅灰标签和彩色数字都能兼顾。verbose=True 时把每个版本的原始结果也打印出来。
    """
    engine = OcrEngine().get()
    notes = []

    best_items = None
    best_quality = -1.0

    for name, variant in build_ocr_variants(crop_bgr, upscale):
        result = engine(variant)
        items = parse_ocr_output(result, upscale, crop_box)

        if len(items) == 0:
            if verbose:
                notes.append("  [%s] 没识别到任何文本" % name)
            continue

        average_score = sum(item["score"] for item in items) / len(items)
        # 质量分：认出的行数越多、置信度越高越好
        quality = len(items) * average_score

        if verbose:
            notes.append(
                "  [%s] %d 行，平均置信度 %.3f"
                % (name, len(items), average_score)
            )
            for item in items:
                notes.append("        %-10s %.3f" % (item["text"], item["score"]))

        if quality > best_quality:
            best_quality = quality
            best_items = items

    if best_items is None:
        return [], notes

    return best_items, notes


def pair_labels_and_values(items):
    """把「标签」和它下面的「数值」配对。

    这张图的结构是：
        已学习      <- 标签
        07:40       <- 数值
        要求学习    <- 标签
        03:00       <- 数值

    规则很简单：从上往下扫，遇到时间格式就归属给最近的那个非时间行。

    返回 [(标签, 数值), ...]
    """
    pairs = []
    pending_label = None

    for item in items:
        text = item["text"].strip()

        if TIME_PATTERN.match(text):
            if pending_label is not None:
                pairs.append((pending_label, text))
                pending_label = None
        else:
            pending_label = text

    return pairs


def extract_times(items):
    """把所有符合 MM:SS 格式的文本挑出来。"""
    times = []
    for item in items:
        matched = TIME_SEARCH_PATTERN.search(item["text"])
        if matched:
            times.append(matched.group(0).replace(" ", ""))
    return times


# ===========================================================================
# 第 4 部分：结果可视化
# ===========================================================================

def draw_result(screen_bgr, match, ocr_items, top_matches=None):
    """在截图副本上画框，用来肉眼确认定位对不对。

    绿色框  = 模板匹配的结果
    黄色框  = 其他候选位置（--top 时）
    蓝色框  = OCR 识别到的每一行
    """
    canvas = screen_bgr.copy()

    if top_matches is not None and len(top_matches) > 1:
        for index in range(1, len(top_matches)):
            x, y, score = top_matches[index]
            cv2.rectangle(
                canvas,
                (x, y),
                (x + match["width"], y + match["height"]),
                (0, 215, 255),
                2,
            )
            cv2.putText(
                canvas, "#%d" % (index + 1), (x, max(20, y - 6)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 215, 255), 2,
            )

    cv2.rectangle(
        canvas,
        (match["x"], match["y"]),
        (match["x"] + match["width"], match["y"] + match["height"]),
        (0, 255, 0),
        2,
    )
    cv2.putText(
        canvas,
        "MATCH score=%.3f scale=%.2f" % (match["score"], match["scale"]),
        (match["x"], max(20, match["y"] - 8)),
        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2,
    )

    for item in ocr_items:
        (x0, y0), (x1, y1) = item["box"]
        cv2.rectangle(canvas, (int(x0), int(y0)), (int(x1), int(y1)), (255, 128, 0), 1)

    return canvas


def save_debug_image(image_bgr, prefix="annotated"):
    """把标注图存到 debug/ 目录，返回文件路径。"""
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = DEBUG_DIR / ("%s_%s.png" % (prefix, stamp))

    # cv2.imwrite 在非 ASCII 路径上会静默失败，统一用 imencode + 文件写入
    success, buffer = cv2.imencode(".png", image_bgr)
    if success:
        path.write_bytes(buffer.tobytes())
    else:
        raise RuntimeError("图片编码失败，无法保存调试图")
    return path


# ===========================================================================
# 第 5 部分：对外接口 —— 就这一个函数
# ===========================================================================
#
# 上面那一大堆都是内部零件，真正给别人用的是下面这一个 read_study_times()。
#
# 用法：
#     from locate_and_ocr import read_study_times
#
#     times = read_study_times("template.png")     # 抓当前屏幕
#     print(times.learned, times.required)         # 07:40 03:00
#     learned, required = times                    # 也可以直接解包
#
# 返回的是 StudyTimes 具名元组，本质就是 (已学习时间, 要求学习时间) 两元组，
# 认不出来的那一项是 None。

# 返回值的类型。它就是个两元组，可以直接解包，也可以按名字取。
# 只认 ASCII 数字 0-9。
# 不能图省事用 str.isdigit()：它对 '²' 这类上标字符也返回 True，
# 但 int('²') 会直接抛 ValueError。而且 str.isdigit() 对阿拉伯-印度数字
# （如 '٠١٢'）也为 True，虽然 int() 能转，但那不是 OCR 会吐出来的东西，
# 放进来只会掩盖问题。用明确的 [0-9] 匹配最干净。
ASCII_DIGITS_PATTERN = re.compile(r"^[0-9]+$")


def time_text_to_seconds(text):
    """把 "MM:SS" 形式的时长文本转成**总秒数（int）**。转不了就返回 None。

    这个函数是「字符串时长」和「数值时长」之间唯一的转换口，
    StudyTimes.learnedSeconds / requiredSeconds 都走它。

    会吃下这些情况：
        '07:40'  -> 460
        '3:05'   -> 185     （分钟不补零也行）
        '103:00' -> 6180    （分钟可以超过两位）
        '03：00' -> 180     （全角冒号，OCR 有时会吐出来）
        ' 03:00' -> 180     （首尾空白）

    下面这些一律返回 None（**宁可返回 None，也不猜**）：
        非字符串 / 空串 / 冒号数量不对 / 各段不是纯数字
        秒数 >= 60（例如 '3:99'）—— 这种几乎可以断定是 OCR 误读，
            硬算成 279 秒只会把一个错值往下游传，还会让"够了没"的判断出错

    注意单位约定是 **MM:SS（分:秒）**，不是 HH:MM。
    """
    if text is None:
        return None

    if not isinstance(text, str):
        text = str(text)

    cleaned = text.strip()
    if cleaned == "":
        return None

    # 半角冒号 : 和全角冒号 ：都要能拆
    parts = re.split(r"[:：]", cleaned)
    if len(parts) != 2:
        return None

    minute_text = parts[0].strip()
    second_text = parts[1].strip()

    if ASCII_DIGITS_PATTERN.match(minute_text) is None:
        return None
    if ASCII_DIGITS_PATTERN.match(second_text) is None:
        return None

    minutes = int(minute_text)
    seconds = int(second_text)

    if seconds >= 60:
        return None

    return minutes * 60 + seconds


class StudyTimes(namedtuple("StudyTimes", ["learned", "required"])):
    """一次读取的结果：已学习时长、要求学习时长。

    取值方式
    --------
    times.learned          原始文本，例如 '00:06'；认不出来时是 None
    times.required         原始文本，例如 '03:00'；认不出来时是 None
    times.learnedSeconds   已学习时长的**总秒数（int）**，认不出来时是 None
    times.requiredSeconds  要求学习时长的**总秒数（int）**，认不出来时是 None

    它**仍然是个两元组**，所以老的写法一样能用：
        learned, required = times
        times[0] / times[1]
        len(times) == 2

    为什么 Seconds 用 property 而不是多加两个字段
    --------------------------------------------
    如果把它们做成字段，元组长度就变成 4 了，
    `learned, required = times` 这种解包会当场炸掉 —— 那就破坏了原有行为。
    做成 property 则是"按需算出来的"，元素个数严格保持 2 个，其他一律不变。

    Seconds 为什么可能是 None
    ------------------------
    因为底层文本可能是 None（没找到元素 / 那一项没认出来）。
    这时候返回 0 是**错的** —— 那会让「不知道」和「确实学了 0 秒」混成一回事。
    沿用本项目一贯的约定：**宁可为 None，也不猜**。
    调用方判断方式：`if times.learnedSeconds is None: ...`
    """

    # namedtuple 子类的标准写法：不额外开 __dict__，保持轻量
    __slots__ = ()

    @property
    def learnedSeconds(self):
        """已学习时长的总秒数（int）；认不出来时是 None。"""
        return time_text_to_seconds(self.learned)

    @property
    def requiredSeconds(self):
        """要求学习时长的总秒数（int）；认不出来时是 None。"""
        return time_text_to_seconds(self.required)

# 标签的几种可能写法。OCR 偶尔会把「已」认成「己」这类形近字，
# 所以下面做相似度比对之前会先归一化一遍。
LEARNED_LABEL_ALIASES = ["已学习", "已学", "已学习时长", "学习时长"]
REQUIRED_LABEL_ALIASES = ["要求学习", "要求学时", "需要学习", "要求时长"]
# 标签相似度低于这个值就不认，宁可为 None 也不瞎猜
LABEL_SIMILARITY_THRESHOLD = 0.62


def _normalize_label(text):
    """归一化标签文字：去空白 + 修常见形近字误认。"""
    cleaned = text.strip()
    cleaned = cleaned.replace(" ", "").replace("\u3000", "")
    cleaned = cleaned.replace("己", "已")   # 己/已 是 OCR 高频混淆
    cleaned = cleaned.replace("耍", "要")   # 耍/要
    cleaned = cleaned.replace("泶", "学")
    return cleaned


def _label_similarity(text, aliases):
    """返回 text 与一组别名里的最高相似度（0~1）。"""
    best = 0.0
    for alias in aliases:
        ratio = difflib.SequenceMatcher(None, text, alias).ratio()
        if ratio > best:
            best = ratio
    return best


def _classify_label(text):
    """判断一行文字是哪个标签。

    返回 'learned' / 'required' / None（认不出来）。

    注意「已学习」和「要求学习」有公共子串，相似度天然不低，
    所以必须**在所有别名里取最高分**再比大小，不能只跟单个别名比。
    """
    cleaned = _normalize_label(text)
    if cleaned == "":
        return None

    learned_score = _label_similarity(cleaned, LEARNED_LABEL_ALIASES)
    required_score = _label_similarity(cleaned, REQUIRED_LABEL_ALIASES)

    if max(learned_score, required_score) < LABEL_SIMILARITY_THRESHOLD:
        return None
    if learned_score >= required_score:
        return "learned"
    return "required"


def _extract_two_times(items, verbose=False):
    """从 OCR 结果里抽出「已学习时间」和「要求学习时间」。

    两条路子，从可靠到兜底依次试：

      路子 A（看标签文字）：按上下位置，把「标签行」和它下面最近的「时间行」配成对，
              再用标签文字判断这一对是「已学习」还是「要求学习」。
              最可靠，因为它真的读懂了文字。

      路子 B（纯按纵向顺序兜底）：万一标签没认出来（比如浅灰小字漏检），
              就按界面固定布局认定：上面那个时间是已学习，下面那个是要求学习。

    返回 (已学习时间, 要求学习时间, 用了哪条路子的说明文字)
    """
    # 先把所有时间行挑出来，带上它在 items 里的下标（items 已按从上到下排好序）
    time_entries = []
    for index, item in enumerate(items):
        matched = TIME_SEARCH_PATTERN.search(item["text"])
        if matched:
            time_entries.append((index, matched.group(0).replace(" ", "")))

    if len(time_entries) == 0:
        return None, None, "一行时间都没识别到"

    # ---------- 路子 A：扫一遍，给每个时间行找到它上面的标签行 ----------
    assigned = {}          # 'learned' / 'required' -> (下标, 时间文本)
    last_label = None      # 最近一个"不是时间"的行

    for index, item in enumerate(items):
        text = item["text"]

        if TIME_SEARCH_PATTERN.search(text):
            if last_label is not None:
                key = _classify_label(last_label)
                if key is not None and key not in assigned:
                    assigned[key] = (index, text.replace(" ", "").strip())
            last_label = None
        else:
            last_label = text

    if "learned" in assigned and "required" in assigned:
        return assigned["learned"][1], assigned["required"][1], "标签语义配对"

    # ---------- 路子 B：按纵向顺序兜底 ----------
    ordered_values = [value for _, value in time_entries]

    if len(ordered_values) >= 2:
        # 两个标签都没认出来 -> 纯按顺序
        if len(assigned) == 0:
            return ordered_values[0], ordered_values[1], "纯纵向顺序兜底"

        # 认出了其中一个，另一个用顺序补齐（注意要按"下标不同"来取，
        # 不能按"值不同"，否则两个时间恰好一样时就卡住了）
        if "learned" in assigned:
            learned_index = assigned["learned"][0]
            for index, value in time_entries:
                if index != learned_index:
                    return assigned["learned"][1], value, "语义 + 顺序兜底"
            return assigned["learned"][1], None, "只认出已学习"

        required_index = assigned["required"][0]
        for index, value in time_entries:
            if index != required_index:
                return value, assigned["required"][1], "语义 + 顺序兜底"
        return None, assigned["required"][1], "只认出要求学习"

    # ---------- 只识别到一个时间 ----------
    only_value = ordered_values[0]
    if "learned" in assigned:
        return only_value, None, "只认出已学习"
    if "required" in assigned:
        return None, only_value, "只认出要求学习"

    # 连标签都没认出来。按布局看最上面那个是已学习，但这属于猜测，
    # 所以只填 learned，required 老实留 None，不编。
    return only_value, None, "只认出一个时间，按布局暂当作已学习"


def read_study_times(example_image, screen_image=None, threshold=DEFAULT_THRESHOLD,
                     trim=True, mode="gray", scale_range=(0.5, 2.0),
                     ocr_upscale=DEFAULT_UPSCALE, coarse_downscale=2, verbose=False):
    """【对外主函数】输入一张示例图，返回「已学习」和「要求学习」的时间。

    参数
    ----
    example_image : str | Path | numpy.ndarray
        示例图（模板）。就是你想在屏幕上找的那块元素的样子，比如 template.png。
        支持传文件路径，也支持直接传已经读好的 BGR 数组。

    screen_image : str | Path | numpy.ndarray | None
        要在哪张图里找。
          - 不传（None）：**实时截取当前屏幕** —— 这是平时的用法。
          - 传图片：在该图片里找，适合离线调试 / 自动化测试 / 处理已有截图。
            此时它和真实屏幕尺寸可能不同，所以不会去动鼠标。

    threshold : float
        模板匹配得分阈值。低于它就直接判定「没找到」，返回 (None, None)。
        默认 0.70。**不要为了"让它找到"而调低** —— 那只会把错误位置当结果。

    trim : bool
        是否先裁掉示例图四周的纯色背景再匹配。默认 True。
        背景占比高时（比如这张 86% 是背景色）开启能显著提高匹配精度。

    mode : str
        匹配方式：'gray'（灰度，默认）/ 'edge'（边缘，界面换配色时更抗打）
        / 'color'（彩色）。

    scale_range : (float, float)
        缩放扫描范围。目标在屏幕上的显示比例可能和示例图不同
        （系统缩放 100%/125%/150%，或界面自身缩放），所以要扫一遍。

    ocr_upscale : float
        OCR 前的放大倍数，默认 3.0。小字放大后识别率明显更高。

    coarse_downscale : int
        粗扫时把屏幕缩小几倍，默认 2。这是纯性能开关，不影响最终精度：
        粗扫只负责"大概在哪、大概多大"，位置和倍率最终由全分辨率精修重算。
        实测 3200x2000 屏幕上，设为 1（不缩）要 2.75 秒，设为 2 只要 0.67 秒。
        只有在排查"明明在屏幕上却找不到"这类问题时，才建议临时设成 1 对照。

    verbose : bool
        是否打印中间过程（匹配得分、OCR 每行结果、用了哪条兜底路子）。

    返回
    ----
    StudyTimes(learned, required)
        一个两元组，可以直接 `learned, required = read_study_times(...)` 解包，
        也可以 `times.learned` / `times.required` 按名字取。
        认不出来的那一项是 None。

        例：StudyTimes(learned='07:40', required='03:00')

    什么时候会返回 None
    ------------------
      - 模板在屏幕上找不到（得分低于 threshold）-> 两个都是 None
      - 找到了但 OCR 没认出时间 -> 对应项是 None

    这两个函数的约定是一致的：**宁可为 None，也不猜**。调用方拿 None 去做判断，
    比拿一个看起来像模像样但其实错的数字安全得多。

    例子
    ----
    >>> times = read_study_times("template.png")
    >>> learned, required = times
    >>> if learned and required:
    ...     print("已学习 %s，要求 %s" % (learned, required))
    """
    # ---------- 1. 读示例图，必要时裁掉纯色背景 ----------
    if isinstance(example_image, np.ndarray):
        template_bgr = example_image
    else:
        template_bgr = load_image_bgr(example_image)

    if template_bgr is None or template_bgr.size == 0:
        raise ValueError("示例图读不出来或者是空的：%r" % (example_image,))

    if trim:
        content_x, content_y, content_w, content_h = find_content_box(template_bgr)
        template_bgr = template_bgr[content_y:content_y + content_h,
                                    content_x:content_x + content_w]

    if template_bgr.size == 0:
        raise ValueError("示例图裁边之后变成空的了，检查一下图片是不是整张纯色。")

    # ---------- 2. 拿到"当前屏幕" ----------
    if screen_image is None:
        screen_bgr = grab_screen_bgr()
        source_name = "实时截屏"
    else:
        if isinstance(screen_image, np.ndarray):
            screen_bgr = screen_image
        else:
            screen_bgr = load_image_bgr(screen_image)
        source_name = "指定图片"

    if verbose:
        log("[read_study_times] 来源=%s，屏幕 %d x %d，示例图 %d x %d"
            % (source_name, screen_bgr.shape[1], screen_bgr.shape[0],
               template_bgr.shape[1], template_bgr.shape[0]))

    # ---------- 3. 模板匹配定位 ----------
    screen_m = to_match_space(screen_bgr, mode)
    template_m = to_match_space(template_bgr, mode)

    match, notes = match_multiscale(
        screen_m, template_m, method_name="ccoef",
        low=scale_range[0], high=scale_range[1],
        coarse_downscale=max(1, coarse_downscale),
    )

    if verbose:
        for note in notes:
            log("    " + note)

    if match is None:
        if verbose:
            log("    [结果] 缩放范围内一次匹配都没跑成（模板比屏幕还大？）")
        return StudyTimes(None, None)

    if match["score"] < threshold:
        if verbose:
            log("    [结果] 没找到可信位置：最高分 %.4f < 阈值 %.2f"
                % (match["score"], threshold))
        return StudyTimes(None, None)

    if verbose:
        log("    [定位] 得分 %.4f，缩放 x%.2f，左上 (%d, %d)，尺寸 %d x %d"
            % (match["score"], match["scale"], match["x"], match["y"],
               match["width"], match["height"]))

    # ---------- 4. 裁剪 + OCR ----------
    crop_bgr, crop_box = crop_region(
        screen_bgr, match["x"], match["y"], match["width"], match["height"], padding=6
    )

    items, _ = run_ocr(crop_bgr, crop_box, ocr_upscale, verbose=verbose)

    if len(items) == 0:
        if verbose:
            log("    [OCR] 一行都没认出来。")
        return StudyTimes(None, None)

    if verbose:
        for item in items:
            log("    [OCR] %-12s %.3f" % (item["text"], item["score"]))

    # ---------- 5. 抽出两个时间 ----------
    learned, required, how = _extract_two_times(items, verbose=verbose)

    if verbose:
        log("    [配对] 方式=%s  ->  已学习=%s，要求学习=%s"
            % (how, learned, required))

    return StudyTimes(learned, required)


# ===========================================================================
# 第 6 部分：命令行参数与主流程
# ===========================================================================

def parse_arguments():
    parser = argparse.ArgumentParser(
        description="在屏幕上定位模板图，并对定位到的区域做 OCR",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE),
                        help="模板图片路径（默认 template.png）")
    parser.add_argument("--image", default=None,
                        help="不截屏，改用这张图片当作'屏幕'（离线调试用）")
    parser.add_argument("--mode", default="gray", choices=["gray", "edge", "color"],
                        help="匹配方式：gray 灰度(默认) / edge 边缘 / color 彩色")
    parser.add_argument("--method", default="ccoef", choices=["ccoef", "ccorr"],
                        help="匹配算法：ccoef 去均值归一化(默认) / ccorr 归一化相关")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help="匹配得分阈值，低于它认为没找到（默认 %.2f）" % DEFAULT_THRESHOLD)
    parser.add_argument("--scale-range", default="0.5,2.0",
                        help="缩放扫描范围，格式 lo,hi（默认 0.5,2.0）")
    parser.add_argument("--trim", action="store_true",
                        help="匹配前先裁掉模板四周的纯色背景（背景占比大时推荐）")
    parser.add_argument("--roi", default=None,
                        help="只在屏幕的这个区域内找，格式 x,y,w,h（截图像素）")
    parser.add_argument("--top", type=int, default=1,
                        help="输出前 N 个候选位置（默认 1）")
    parser.add_argument("--no-ocr", action="store_true", help="跳过 OCR，只做定位")
    parser.add_argument("--upscale", type=float, default=DEFAULT_UPSCALE,
                        help="OCR 前放大倍数（默认 %.1f）" % DEFAULT_UPSCALE)
    parser.add_argument("--move-mouse", action="store_true",
                        help="把鼠标移到定位到的元素中心（只移动，不点击）")
    parser.add_argument("--debug", action="store_true", help="保存标注图到 debug/")
    parser.add_argument("--verbose", action="store_true", help="打印匹配/OCR 的中间细节")
    parser.add_argument("--watch", action="store_true", help="循环执行，Ctrl+C 退出")
    parser.add_argument("--interval", type=float, default=2.0,
                        help="--watch 模式下的间隔秒数（默认 2.0）")
    parser.add_argument("--info", action="store_true",
                        help="只打印屏幕信息和缩放比例，然后退出")
    parser.add_argument("--monitor", type=int, default=1,
                        help="mss 显示器编号：1=主显示器(默认)，0=所有显示器并集，2+=副屏")
    parser.add_argument("--no-mss", action="store_true",
                        help="不使用 mss，改用 pyautogui 截屏")
    parser.add_argument("--coarse-downscale", type=int, default=2,
                        help="粗扫时把屏幕缩小几倍（默认 2，设 1 = 不缩、最准但最慢）")

    return parser.parse_args()


def parse_roi(roi_text, image_width, image_height):
    """解析 --roi 的 x,y,w,h，并裁到图片范围内。"""
    parts = roi_text.split(",")
    if len(parts) != 4:
        raise ValueError("--roi 格式应该是 x,y,w,h，例如 800,300,600,500")

    x = int(parts[0])
    y = int(parts[1])
    width = int(parts[2])
    height = int(parts[3])

    x = max(0, min(x, image_width - 1))
    y = max(0, min(y, image_height - 1))
    width = max(1, min(width, image_width - x))
    height = max(1, min(height, image_height - y))

    return x, y, width, height


def print_screen_info(args):
    """打印屏幕尺寸和缩放信息，排查坐标错位时很有用。"""
    logical_width, logical_height = pyautogui.size()
    screen_bgr = grab_screen_bgr(use_mss=not args.no_mss, monitor_index=args.monitor)
    image_height, image_width = screen_bgr.shape[:2]
    scale_x, scale_y = get_coord_scale(image_width, image_height)

    log("=" * 62)
    log("屏幕信息")
    log("=" * 62)
    log("pyautogui.size() 逻辑尺寸 : %d x %d" % (logical_width, logical_height))
    log("截图实际尺寸              : %d x %d" % (image_width, image_height))
    log("坐标换算比例              : x%.4f, y%.4f" % (scale_x, scale_y))

    if abs(scale_x - 1.0) > 0.01 or abs(scale_y - 1.0) > 0.01:
        percent = (1.0 / scale_x) * 100.0
        log("→ 检测到系统显示缩放约 %.0f%%，截图坐标必须乘 %.4f 才能当鼠标坐标用。"
            % (percent, scale_x))
    else:
        log("→ 截图与逻辑坐标 1:1，不需要换算。")
    log("=" * 62)


def run_once(args, template_bgr):
    """执行一轮「截屏 -> 定位 -> OCR」，返回结果字典 或 None。"""
    # ---------- 1. 拿到屏幕图 ----------
    if args.image is not None:
        screen_bgr = load_image_bgr(args.image)
        source_name = "图片 %s" % args.image
    else:
        screen_bgr = grab_screen_bgr(use_mss=not args.no_mss, monitor_index=args.monitor)
        source_name = "实时截屏"

    image_height, image_width = screen_bgr.shape[:2]

    # ---------- 2. 需要的话限定搜索区域 ----------
    offset_x = 0
    offset_y = 0
    search_bgr = screen_bgr

    if args.roi is not None:
        roi_x, roi_y, roi_width, roi_height = parse_roi(args.roi, image_width, image_height)
        search_bgr = screen_bgr[roi_y:roi_y + roi_height, roi_x:roi_x + roi_width]
        offset_x = roi_x
        offset_y = roi_y

    # ---------- 3. 模板匹配 ----------
    search_m = to_match_space(search_bgr, args.mode)
    template_m = to_match_space(template_bgr, args.mode)

    low_text, high_text = args.scale_range.split(",")
    scale_low = float(low_text)
    scale_high = float(high_text)

    match, notes = match_multiscale(
        search_m, template_m, method_name=args.method,
        low=scale_low, high=scale_high,
        coarse_downscale=max(1, args.coarse_downscale),
    )

    if args.verbose:
        for note in notes:
            log("  " + note)

    if match is None:
        log("[结果] 模板比屏幕还大，缩放范围内一次匹配都没跑成。")
        return None

    # 把 ROI 偏移加回去，得到全屏截图坐标
    match["x"] += offset_x
    match["y"] += offset_y

    # ---------- 4. 阈值判定 ----------
    if match["score"] < args.threshold:
        log("[结果] 没找到可信的匹配。最高分 %.4f，低于阈值 %.2f。"
            % (match["score"], args.threshold))
        log("       建议：降低 --threshold，或换 --mode edge / 加 --trim 再试。")
        return None

    # ---------- 5. 多个候选 ----------
    top_matches = None
    if args.top > 1:
        score_map = cv2.matchTemplate(search_m, _scaled_template(template_m, match["scale"]),
                                      cv2.TM_CCOEFF_NORMED if args.method == "ccoef"
                                      else cv2.TM_CCORR_NORMED)
        top_matches = find_top_matches(
            score_map, match["width"], match["height"], args.threshold, args.top
        )
        top_matches = [(x + offset_x, y + offset_y, s) for (x, y, s) in top_matches]

    # ---------- 6. 打印定位结果 ----------
    scale_x, scale_y = get_coord_scale(image_width, image_height)

    center_x_px = match["x"] + match["width"] / 2.0
    center_y_px = match["y"] + match["height"] / 2.0
    center_x_screen = center_x_px * scale_x
    center_y_screen = center_y_px * scale_y

    log("-" * 62)
    log("来源        : %s" % source_name)
    log("截图尺寸    : %d x %d" % (image_width, image_height))
    log("匹配得分    : %.4f  (阈值 %.2f)" % (match["score"], args.threshold))
    log("最佳缩放    : x%.2f" % match["scale"])
    log("截图内位置  : 左上 (%d, %d)  尺寸 %d x %d"
        % (match["x"], match["y"], match["width"], match["height"]))

    if args.image is not None:
        # --image 模式喂进来的是外部图片，尺寸和真实屏幕不一定一致，
        # 这时候"坐标换算"是没意义的，必须说清楚，免得误导。
        log("图像内坐标  : 中心 (%.0f, %.0f)" % (center_x_px, center_y_px))
        log("[注意] --image 用的是外部图片，它和真实屏幕尺寸不一定一致，")
        log("       上面的换算比例（%.3f）只在「该图片正好是全屏截图」时才成立。" % scale_x)
        log("       离线调试请只看「截图内位置」，别拿这个坐标去动鼠标。")
    else:
        log("鼠标可用坐标: 中心 (%.0f, %.0f)  [已按 %.3f 的比例换算]"
            % (center_x_screen, center_y_screen, scale_x))

    if args.trim:
        log("位置说明    : 已开启 --trim，上面的框是模板裁掉纯色背景后的「内容外框」，")
        log("              比模板原始边界更贴合元素本身，这也是 OCR 实际用到的区域。")

    if top_matches is not None and len(top_matches) > 1:
        log("其他候选    :")
        for index in range(1, len(top_matches)):
            x, y, score = top_matches[index]
            log("    #%d  左上 (%d, %d)  score=%.4f" % (index + 1, x, y, score))

    # ---------- 7. 裁剪 + OCR ----------
    ocr_items = []
    crop_path = None

    crop_bgr, crop_box = crop_region(
        screen_bgr, match["x"], match["y"], match["width"], match["height"], padding=6
    )

    # 把裁剪的区域也存下来，方便单独看 OCR 到底看到了什么
    if args.debug:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        crop_path = DEBUG_DIR / ("crop_%s.png" % stamp)
        success, buffer = cv2.imencode(".png", crop_bgr)
        if success:
            crop_path.write_bytes(buffer.tobytes())

    if not args.no_ocr:
        log("-" * 62)
        log("OCR 区域    : 截图坐标 (%d, %d) %d x %d"
            % (crop_box["x"], crop_box["y"], crop_box["width"], crop_box["height"]))

        ocr_items, ocr_notes = run_ocr(crop_bgr, crop_box, args.upscale, verbose=args.verbose)

        if args.verbose:
            for note in ocr_notes:
                log(note)

        if len(ocr_items) == 0:
            log("[OCR] 一行都没识别出来。可以试试加大 --upscale 或提高截图清晰度。")
        else:
            log("[OCR] 识别到 %d 行：" % len(ocr_items))
            for item in ocr_items:
                log("      %-12s  置信度 %.3f" % (item["text"], item["score"]))

            times = extract_times(ocr_items)
            if len(times) > 0:
                log("[OCR] 提取到的时间值：%s" % "  ".join(times))

            pairs = pair_labels_and_values(ocr_items)
            if len(pairs) > 0:
                log("[OCR] 标签 -> 数值：")
                for label, value in pairs:
                    log("      %s  ->  %s" % (label, value))

    # ---------- 8. 调试图 / 移动鼠标 ----------
    if args.debug:
        canvas = draw_result(screen_bgr, match, ocr_items, top_matches)
        annotated_path = save_debug_image(canvas)
        log("-" * 62)
        log("调试图已保存: %s" % annotated_path)
        if crop_path is not None:
            log("OCR 裁剪图  : %s" % crop_path)

    if args.move_mouse:
        if args.image is not None:
            # --image 模式下坐标基准是那张外部图片，动鼠标是没有意义的
            log("[跳过] --image 模式下的坐标不能用来控制鼠标，已忽略 --move-mouse。")
        else:
            pyautogui.moveTo(int(round(center_x_screen)), int(round(center_y_screen)),
                             duration=0.25)
            log("鼠标已移动到 (%.0f, %.0f)" % (center_x_screen, center_y_screen))

    return {
        "match": match,
        "ocr_items": ocr_items,
        "top_matches": top_matches,
        "center_screen": (center_x_screen, center_y_screen),
    }


def _scaled_template(template_m, scale):
    """按比例缩放模板（--top 复算得分图时用）。"""
    if abs(scale - 1.0) < 1e-6:
        return template_m
    if scale < 1.0:
        interpolation = cv2.INTER_AREA
    else:
        interpolation = cv2.INTER_CUBIC
    return cv2.resize(template_m, None, fx=scale, fy=scale, interpolation=interpolation)


def main():
    args = parse_arguments()

    if args.info:
        print_screen_info(args)
        return 0

    template_path = Path(args.template)
    if not template_path.exists():
        log("[错误] 找不到模板图：%s" % template_path)
        log("       可以用 capture_template.py 从屏幕上重新截一块。")
        return 2

    template_bgr = load_image_bgr(template_path)
    template_height, template_width = template_bgr.shape[:2]

    # --trim：裁掉四周纯色背景后再匹配
    if args.trim:
        content_x, content_y, content_width, content_height = find_content_box(template_bgr)
        template_bgr = template_bgr[
            content_y:content_y + content_height,
            content_x:content_x + content_width,
        ]

    log("=" * 62)
    log("模板        : %s" % template_path.name)
    log("模板原始尺寸: %d x %d%s"
        % (template_width, template_height,
           "  -> 裁边后 %d x %d" % (template_bgr.shape[1], template_bgr.shape[0])
           if args.trim else ""))
    log("匹配模式    : %s / %s" % (args.mode, args.method))
    log("=" * 62)

    if not args.watch:
        result = run_once(args, template_bgr)
        return 0 if result is not None else 1

    log("进入 --watch 模式，每 %.1f 秒一次，Ctrl+C 退出。" % args.interval)
    round_index = 0
    while True:
        round_index += 1
        log("")
        log("### 第 %d 轮  %s ###" % (round_index, time.strftime("%H:%M:%S")))
        try:
            run_once(args, template_bgr)
        except KeyboardInterrupt:
            raise
        except Exception as error:
            log("[警告] 这一轮出错：%s: %s" % (type(error).__name__, error))
        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("")
        log("已手动中断。")
        sys.exit(130)
