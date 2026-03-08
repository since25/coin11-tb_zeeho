# Android Automation Scripts

本项目基于 `uiautomator2`，用于自动化执行淘宝、极核、起点读书等任务。

## 1. 环境要求

1. 操作系统：macOS（已验证，Apple Silicon）。
2. Python：`3.11`（推荐并已验证）。
3. Android 调试：已安装并可用 `adb`。
4. 手机端：开启开发者模式和 USB/Wi-Fi 调试，并允许调试授权。

## 2. 从 clone 到运行

1. 克隆仓库：

```bash
git clone git@github.com:since25/coin11-tb_zeeho.git
cd coin11-tb_zeeho
```

2. 创建并激活虚拟环境（Python 3.11）：

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -V
```

3. 安装依赖：

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

4. 确认设备连接：

```bash
adb devices
```

## 3. 脚本说明与运行方式

1. 淘宝金币任务：

```bash
. .venv/bin/activate && PYTHONUNBUFFERED=1 python -u taobao_coins_task.py
```

2. 极核签到/点赞：

```bash
. .venv/bin/activate && PYTHONUNBUFFERED=1 python -u zeeho_task.py
```

3. 起点福利中心（老版本综合脚本）：

```bash
. .venv/bin/activate && PYTHONUNBUFFERED=1 python -u qidian_task.py
```

4. 起点福利中心主任务（当前主脚本）：

```bash
. .venv/bin/activate && PYTHONUNBUFFERED=1 python -u qidianfuli_task.py
```

5. 起点抽奖任务独立测试脚本（用于单独调试“做任务可抽奖”链路）：

```bash
. .venv/bin/activate && PYTHONUNBUFFERED=1 python -u qidian_lottery_task.py
```

## 4. OCR 说明

1. macOS 下优先使用 `ocrmac`（Apple Vision）。
2. 若 `ocrmac` 失败，自动回退 `easyocr`。
3. 回退到 `easyocr` 时，优先尝试 Apple MPS/GPU，失败再回退 CPU。

## 5. 依赖检查结论

按当前代码实际 import 检查后，补充了以下此前遗漏的直接依赖：

1. `numpy`
2. `Pillow`
3. `selenium`

`requirements.txt` 已更新。

## 6. 调试常用命令

1. 当前前台页面：

```bash
adb shell dumpsys window | grep mCurrentFocus
```

2. 截图：

```bash
adb shell screencap -p /sdcard/screenshot.png
adb pull /sdcard/screenshot.png .
adb shell rm /sdcard/screenshot.png
```

3. 导出页面层级：

```bash
adb shell uiautomator dump /sdcard/window_dump.xml
adb pull /sdcard/window_dump.xml .
adb shell rm /sdcard/window_dump.xml
```
