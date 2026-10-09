import sys
from time import sleep
import os
import pyautogui
from inputimeout import inputimeout, TimeoutOccurred

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from locate_and_ocr import read_study_times
from find_edge import close_window
from read_and_open_link import make_link_opener
from click_by_image import click_image
from advanced_print import print_pro


def main():
    
    previousLeranedSeconds = 0
    state = None
    while True:
        opener = make_link_opener("textCourses.json", state=state)
        link = opener("next")
        state=opener.state()
        if link is None:
            print_pro("文本浏览性课程已刷完！严肃开刷视频课程喵...", color="cyan", timestamp=True)
            break
        print_pro(f"正在打开： {link.courseName} URL:  {link.url}", timestamp=True)
        hwnd=opener.hwnd
        if link is None:
            break
        print_pro("正在等待页面加载, 请主人耐心等待喵...")
        sleep(5)
        while True:
            try:
                times = read_study_times("template.png")
            except OSError as error:
                print_pro("模板文件不可用：%s" % error, color="red")          # 重试无意义
                print_pro("看下文档，自己试着截一个图放到当前目录下，命名为 template.png", color="red")
                print_pro("或者联系开发者解决喵", color="red")
                return 0
            except (ValueError, ImportError,
                    TypeError, AttributeError, IndexError) as error:
                print_pro("参数或调用姿势错了喵：%s" % error, color="red")      # 重试无意义
                print_pro("请联系开发者解决喵", color="red")
                return 0
            except Exception as error:
                sleep(3)                                     # 偶发问题，值得重试
                continue
            else:
                if times.learned is None and times.required is None:
                    print_pro("没找到计时器喵", color="yellow")
                    print_pro("请确认：计时器正显示在屏幕上，且没被别的窗口挡住。", color="yellow")
                    print_pro("对开发者：排查时可以在read_study_times里加参数verbose=True看中间过程喵")
                    sleep(3)                          # 可能时机不对，重试
                    
                    continue
            # 打开页面，刷时长
            learned = times.learned
            required = times.required
            learnedSeconds = times.learnedSeconds
            requiredSeconds = times.requiredSeconds
            print_pro(f"已学时长：{learned}，要求时长：{required}", color="cyan", timestamp=True)
            if learnedSeconds is not None and requiredSeconds is not None:
                if learnedSeconds >= requiredSeconds:
                    print_pro("本节已学完，请等待数据上传，然后窗口会自动关闭", color="green", timestamp=True)
                    sleep(20) # 页面每隔15s上传一次学习时长，停留一段时间保证数据上传
                    close_window(hwnd)
                    break
                if learnedSeconds == previousLeranedSeconds:
                    print_pro("学习时长未更新，可能是弹出了5分钟弹窗，正在尝试使用Ctrl+R刷新页面...", color="yellow", timestamp=True)
                    sleep(1)
                    pyautogui.hotkey('ctrl', 'r')
                    continue
            else:
                print_pro("返回的学习时长数据有异常。", color="yellow")
                print_pro(f"{learnedSeconds}   {requiredSeconds}")
                print_pro(f"{type(learnedSeconds)}   {type(requiredSeconds)}")
            previousLeranedSeconds = learnedSeconds
            sleep(20)

    state = None

    while True:
        print_pro("开刷视频课喵", color="cyan", timestamp=True)
        opener = make_link_opener("videoCourses.json", state=state)
        link = opener("next")
        state=opener.state()
        if link is None:
            print_pro("视频课也刷完了喵~", color="green", timestamp=True)
            break
        print_pro(f"正在打开： {link.courseName} URL:  {link.url}", timestamp=True)
        hwnd=opener.hwnd
        if link is None:
            break

        keyboardInput = "Text"

        try:
            keyboardInput = inputimeout("如果主人确认本节视频课已学完，可在10s内按回车切到下一节喵~", timeout=10)
            print_pro(keyboardInput)
        except TimeoutOccurred:
            print_pro("主人没有确认，正在尝试开始播放本节课喵")
        
        if keyboardInput == "":
            print_pro("主人确认本节视频课已学完，正在切到下一节喵~")
            close_window(hwnd)
            continue

        print_pro("正在等待页面加载, 请主人耐心等待喵...")
        sleep(5)

        status=click_image(image_name="videoCourseFinished.png", confidence=0.9, dry_run=True)
        if status:
            print_pro("本节已学完，请等待数据上传，然后窗口会自动关闭", color="green", timestamp=True)
            sleep(20) # 页面每隔15s上传一次学习时长，停留一段时间保证数据上传
            close_window(hwnd)
            continue
        
        while True:
            try:
                print_pro("尝试点击开始播放")
                clickToPlay = click_image("videoCourseTarget.png", confidence=0.8)
            except FileNotFoundError as exc:
                print_pro(f"图片路径有问题： {exc}", color="red")
                return 0
            except ImportError as exc:
                print_pro(f"缺依赖： {exc}", color="red")
                return 0
            except ValueError as exc:
                print_pro(f"参数不合法： {exc}", color="red")
                return 0
            # 挂机等待，刷时长
            if clickToPlay:
                print_pro(f"已点击播放按钮。视频时长:  {link.requiredStudyTime} 秒。请主人耐心等待喵...")
                break
        while True:
                    try:
                        times = read_study_times(example_image="template-videoCourse.png")
                    except OSError as error:
                        print_pro("模板文件不可用：%s" % error, color="red")          # 重试无意义
                        print_pro("看下文档，自己试着截一个图放到当前目录下，命名为 template-videoCourse.png", color="red")
                        print_pro("或者联系开发者解决喵", color="red")
                        return 0
                    except (ValueError, ImportError,
                            TypeError, AttributeError, IndexError) as error:
                        print_pro("参数或调用姿势错了喵：%s" % error, color="red")      # 重试无意义
                        print_pro("请联系开发者解决喵", color="red")
                        return 0
                    except Exception as error:
                        sleep(3)                                     # 偶发问题，值得重试
                        continue
                    else:
                        if times.learned is None and times.required is None:
                            print_pro("没找到计时器喵", color="yellow")
                            print_pro("请确认：计时器正显示在屏幕上，且没被别的窗口挡住。", color="yellow")
                            print_pro("对开发者：排查时可以在read_study_times里加参数verbose=True看中间过程喵")
                            sleep(3)                          # 可能时机不对，重试
                            continue
                    


                    # 记录时长
                    learned = times.learned
                    required = times.required
                    learnedSeconds = times.learnedSeconds
                    requiredSeconds = times.requiredSeconds
                    print_pro(f"已学时长：{learned}，要求时长：{required}", color="cyan", timestamp=True)
                    if learnedSeconds is not None and requiredSeconds is not None:
                        if learnedSeconds >= requiredSeconds:
                            print_pro("本节已学完，请等待数据上传，然后窗口会自动关闭", color="green", timestamp=True)
                            sleep(20) # 页面每隔15s上传一次学习时长，停留一段时间保证数据上传
                            close_window(hwnd)
                            break
                        
                    else:
                        status=click_image(image_name="videoCourseFinished.png", confidence=0.9, dry_run=True)
                        if status:
                            print_pro("本节已学完，请等待数据上传，然后窗口会自动关闭", color="green", timestamp=True)
                            sleep(20) # 页面每隔15s上传一次学习时长，停留一段时间保证数据上传
                            close_window(hwnd)
                            break
                        else:
                            print_pro("返回的学习时长数据有异常。", color="yellow")
                            print_pro(f"{learnedSeconds}   {requiredSeconds}")
                            print_pro(f"{type(learnedSeconds)}   {type(requiredSeconds)}")
                    sleep(20)


    return 0


if __name__ == "__main__":
    sys.exit(main())
