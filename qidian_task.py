import uiautomator2 as u2
import time
from utils import select_device, start_app, QD_APP, easy_ocr, get_current_app
from PIL import Image
import os

def find_and_click_ocr(d, target_text, retry=3, exact=False):
    """使用 OCR 查找并点击特定文字"""
    for i in range(retry):
        print(f"正在通过 OCR 搜索: {target_text}...")
        screenshot = d.screenshot()
        ocr_res = easy_ocr(screenshot, return_info=True)
        for (bbox, text, prob) in ocr_res:
            if exact:
                match = (target_text == text)
            else:
                match = (target_text in text)
            
            if match:
                center_x = int((bbox[0][0] + bbox[1][0]) // 2)
                center_y = int((bbox[0][1] + bbox[2][1]) // 2)
                d.click(center_x, center_y)
                print(f"OCR 成功点击 '{text}' @ ({center_x}, {center_y})")
                return True
        time.sleep(1)
    return False

def find_text_and_click_button(d, title_keyword, btn_text="去完成", retry=2):
    """
    寻找任务标题并在其对应的水平行寻找按钮。
    """
    for i in range(retry):
        print(f"扫描任务列表: {title_keyword}...")
        screenshot = d.screenshot()
        ocr_res = easy_ocr(screenshot, return_info=True)
        
        target_y = None
        for (bbox, text, prob) in ocr_res:
            if title_keyword in text:
                target_y = (bbox[0][1] + bbox[2][1]) // 2
                print(f"定位到任务 '{text}'，行坐标 Y: {target_y}")
                break
        
        if target_y:
            for (bbox, text, prob) in ocr_res:
                if btn_text in text:
                    btn_y = (bbox[0][1] + bbox[2][1]) // 2
                    if abs(btn_y - target_y) < 150:
                        center_x = int((bbox[0][0] + bbox[1][0]) // 2)
                        center_y = int(btn_y)
                        d.click(center_x, center_y)
                        print(f"点击任务按钮: {title_keyword} -> {text} @ ({center_x}, {center_y})")
                        return True
        time.sleep(1)
    return False

def find_close_button(d):
    """
    多重策略寻找并点击广告关闭按钮 (X)。
    增加基于 UI 层次结构的遍历搜索。
    """
    print("尝试寻找广告关闭按钮...")
    w, h = d.window_size()
    
    # 策略 1: 扫描 UI 层次结构中的所有按钮或点击元素 (最强大)
    print("正在分析 UI 层次结构寻找右上角可点击元素...")
    ui_hierarchy = d.dump_hierarchy()
    import xml.etree.ElementTree as ET
    root = ET.fromstring(ui_hierarchy)
    
    potential_nodes = []
    for node in root.iter('node'):
        if node.get('clickable') == 'true' or node.get('class') == 'android.widget.ImageView':
            bounds = node.get('bounds')
            # bounds 格式: [x1,y1][x2,y2]
            import re
            m = re.findall(r'\d+', bounds)
            if m:
                x1, y1, x2, y2 = map(int, m)
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                # 右上角区域判断：右侧 25% 且 顶部 20%
                if cx > w * 0.75 and cy < h * 0.2:
                    node_info = {
                        'x': cx, 'y': cy, 
                        'text': node.get('text'), 
                        'id': node.get('resource-id'),
                        'desc': node.get('content-desc'),
                        'class': node.get('class')
                    }
                    potential_nodes.append(node_info)
    
    if potential_nodes:
        # 按照“越靠近右上角越优先”排序
        potential_nodes.sort(key=lambda n: (w - n['x']) + n['y'])
        target = potential_nodes[0]
        print(f"层级识别：找到右上角疑似关闭按钮: {target['id'] or target['class']} @ ({target['x']}, {target['y']})")
        d.click(target['x'], target['y'])
        return True

    # 策略 2: 常见关键字
    close_selectors = [
        d(resourceIdMatches=r".*close.*|.*cancel.*|.*exit.*|.*skip.*"),
        d(descriptionMatches=r".*关闭.*|.*跳过.*|.*Close.*|.*Skip.*"),
        d(textMatches=r"跳过|关闭|退出")
    ]
    for sel in close_selectors:
        if sel.exists:
            print(f"选择器命中: {sel.info.get('resourceName', 'Unknown')}")
            sel.click()
            return True

    # 策略 3: OCR
    if find_and_click_ocr(d, "关闭", retry=1): return True
    if find_and_click_ocr(d, "跳过", retry=1): return True
    
    # 策略 4: 盲点 (扩大范围)
    print("层级和 OCR 均失败，执行最后一招：盲点右上角关键位置...")
    盲触点 = [(w - 60, 60), (w - 100, 100), (w - 60, 150)]
    for (cx, cy) in 盲触点:
        d.click(cx, cy)
        time.sleep(0.3)
    
    # 调试记录：如果都失败了，保存一份 dump 以便分析
    if not any(sel.exists for sel in close_selectors):
        with open("ad_error_dump.xml", "w", encoding="utf-8") as f:
            f.write(ui_hierarchy)
        print("已保存当前 UI 布局到 ad_error_dump.xml 供后续分析。")
        
    return True

def handle_ad_playback(d):
    print("进入广告交互流程...")
    time.sleep(3)
    d.swipe_ext("up", scale=0.2)
    time.sleep(1)
    
    if find_and_click_ocr(d, "了解详情", retry=2):
        print("启动任务倒计时：已点击‘了解详情’")
    
    print("循环监测奖励发放状态...")
    reward_confirmed = False
    for attempt in range(16): # 80s
        screenshot = d.screenshot()
        txt = easy_ocr(screenshot)
        if any(keyword in txt for keyword in ["恭喜", "获得", "已发放", "完成", "奖励"]):
            print(f"奖励确认到账！")
            reward_confirmed = True
            break
        print(f"监测中... { (attempt+1)*5 }/80s")
        time.sleep(5)
    
    # 点击关闭
    find_close_button(d)
    time.sleep(3)
    
    # 处理“知道了”
    if not find_and_click_ocr(d, "知道了", retry=3):
        print("未发现‘知道了’弹窗，尝试物理后退...")
        d.press("back")

def qidian_main_tasks(d):
    print("开始起点福利中心综合任务流程...")
    
    # 尽可能多地尝试关闭开屏弹窗
    for _ in range(3):
        d(resourceId="com.qidian.QDReader:id/mini_player_close").click_exists()
        d(resourceId="com.qidian.QDReader:id/ivClose").click_exists()
        time.sleep(1)

    package, activity = get_current_app(d)
    # 检查是否已经在福利中心 (通常是在 BrowserActivity 中)
    if "QDBrowserActivity" not in activity:
        print("未在福利中心，开始执行导航流程...")
        
        # 1. 寻找并点击右下角“我的” (通常 ID 是 f6 或文字“我”)
        me_tab = d(resourceIdMatches=r".*tab_me.*|.*f6.*", text="我的")
        if not me_tab.exists:
            # 备选案：通过坐标点击右下角 (1080/5 * 4.5 左右)
            w, h = d.window_size()
            print("未找到‘我的’按钮，尝试点击屏幕右下角布局...")
            d.click(w * 0.9, h - 100)
        else:
            print("点击进入“我的”页面...")
            me_tab.click()
        
        time.sleep(3)
        
        # 2. 在“我的”页面寻找“福利中心”
        # 有时在屏幕内，有时需要稍微下滑
        benefit_btn = d(text="福利中心")
        if not benefit_btn.exists:
            print("未直接看到福利中心，尝试小幅下滑...")
            d.swipe_ext("up", scale=0.2)
            time.sleep(1)
            benefit_btn = d(text="福利中心")
            
        if benefit_btn.exists:
            print("找到福利中心入口，正在进入...")
            benefit_btn.click()
            time.sleep(8) # 福利中心加载通常很慢
        else:
            print("致命错误：无法在‘我的’页面定位到‘福利中心’入口")
            return
    
    # 确认进入后，开始任务
    print("当前已确保在福利中心，准备执行具体任务...")
    tasks = ["激励任务", "惊喜福利", "3个广告", "1个广告"]
    for task_name in tasks:
        # 重试 2 次找任务，防止加载太慢
        found = False
        for _ in range(2):
            if find_text_and_click_button(d, task_name):
                handle_ad_playback(d)
                print(f"任务阶段结束: {task_name}")
                time.sleep(5)
                found = True
                break
            time.sleep(2)
            
        if not found:
            print(f"当前页面未识别到任务: {task_name}，由于是滑动列表，尝试下滑继续查找...")
            d.swipe_ext("up", scale=0.3)
            time.sleep(2)

def main():
    try:
        device_id = select_device()
        d = u2.connect(device_id)
        qidian_main_tasks(d)
        print("起点福利中心任务全部执行完成。")
    except Exception as e:
        print(f"脚本执行中断: {e}")

if __name__ == "__main__":
    main()
