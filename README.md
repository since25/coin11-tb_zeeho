# Zeeho & Taobao Automation Task

本项目基于 `uiautomator2` 自动化完成淘宝金币任务及极核 (Zeeho) 每日签到/点赞任务。

*   `taobao_coins_task.py`: 淘金币任务脚本。
*   `zeeho_task.py`: 极核 (Zeeho) APP 签到及点赞任务。
*   `utils.py`: 核心工具库。

目前系统已针对 MacOS + Android 环境进行了深度优化（包括依赖包兼容性和 OCR 懒加载）。
$\color{red}{目前的问题是，uiautomator2将列表上滑一页后，获取的数据还是上一页的，这个问题已反馈作者但未解决。}$

```shell
adb shell screencap -p /sdcard/screenshot.png
adb pull /sdcard/screenshot.png .
adb shell rm /sdcard/screenshot.png
```

```shell
adb shell uiautomator dump /sdcard/window_dump.xml
adb pull /sdcard/window_dump.xml .
adb shell rm /sdcard/window_dump.xml
```