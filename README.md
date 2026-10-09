# 兰州交通大学 实验室安全教育平台自动化工具

## 概览

这是一个专为兰州交通大学实验室安全教育平台而设计的自动化工具，基于UI自动化原理设计，具有良好的反检测能力。

实验室安全教育课程繁杂且信息密度低，建议您使用本工具刷学时，然后通过不断刷题来过考试，就像科目一那样。

**警告：本程序不会帮你完成刷题环节。**

驾校教练可以帮你打学时，但是考科目二必须由你本人亲自上阵。

**你必须自行完成刷题环节，并且确保高正确率，因为考试机会只有一次。**

## 架构

主程序为`demo.py`。

`locate_and_ocr.py`：用于寻找学习时长计时器，然后通过OCR读取当前的学习时长。

`advanced_print.py`：提供一个便捷的`print_pro`函数，用于输出彩字和带时间戳的日志。

`click_by_image.py`：用于点击视频课的开始播放按钮。

`edge_open.py`：用于打开Edge浏览器并且最大化窗口。

`read_and_open_link.py`：用于按顺序打开链接。

`edge_win.py`：用于打开、最大化以及关闭Edge窗口。

## 系统要求

本项目支持Windows10、Windows11。更旧的Windows暂时不受支持。

必须安装一个Microsoft Edge浏览器。一般来说，你的设备上自带Microsoft Edge。

以下是项目功能与系统版本对应表。


| 功能             | Windows 10 | Windows 10 2004 之前 | Windows 11 |
| :--------------- | ---------- | :------------------- | ---------- |
| 一键离线安装     | ✅         | ✅                   | ✅         |
| 基本刷课         | ✅         | ✅                   | ✅         |
| 自带的现代化终端 | ✅         | ×                   | ✅         |

## 使用

按以下步骤，依次执行即可。

### 确认系统要求

- 系统版本为Windows10或Windows11。
- 已安装Microsoft Edge浏览器。
- 一般来说，你的设备上自带Microsoft Edge。

### 调节屏幕设置

- 分辨率改为1920x1080
- 缩放比调整为100%
- 关闭HDR

参考教程：[调整Windows屏幕分辨率](https://support.microsoft.com/zh-cn/windows/hardware/display-graphics/change-your-screen-resolution-and-layout-in-windows)

### 一键安装并开始使用

双击`启动程序.exe`即可。它会自动配置python+venv。一切需要的pip包都已经包含在程序内，因此无需担心网络问题。

## 构建

运行`./code/tools/launcher/build.ps1`，构建一键启动器

如果python代码引入了新的依赖，请要求你的AI Agent重新配置此项目的离线依赖包。

运行`./code/install/scripts/pack_dist.ps1`即可进行项目打包，生成一个可以复制到新机器上运行的文件夹。

打包后的文件夹存放在项目的上级目录内（比如项目在./LabSecAutomation，那么打包的文件夹在./LabSecAutomation-dist-yyyymmdd），不会包含项目内的AI Agent配置、.venv等内容。你可以手动打一个压缩包，分发给他人。

向他人分发时，必须打包一次，用打包后的文件进行相应操作。

## AI使用报告

除了`demp.py`、`advanced_print.py`，其他模块、安装程序都是AI写的。
