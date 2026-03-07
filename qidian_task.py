import uiautomator2 as u2
import time
from utils import select_device, start_app, QD_APP, easy_ocr, get_current_app
from PIL import Image

def find_text_and_click_button(d, title_keyword, btn_text="去完成", retry=2):
    """
    在页面中寻找 title_keyword，并在其附近寻找 btn_text 并点击。
    针对 WebView 中多个“去完成”按钮的情况。
    """
    for i in range(retry):
        print(f"正在寻找任务: {title_keyword} 并点击 '{btn_text}'...")
        screenshot = d.screenshot()
        ocr_res = easy_ocr(screenshot, return_info=True)
        
        target_y = None
        # 首先寻找标题行的 Y 轴位置
        for (bbox, text, prob) in ocr_res:
            if title_keyword in text:
                target_y = (bbox[0][1] + bbox[2][1]) // 2
                print(f"找到任务标题 '{text}'，Y轴位置: {target_y}")
                break
        
        if target_y:
            # 在该 Y 轴附近寻找“去完成”按钮
            for (bbox, text, prob) in ocr_res:
                if btn_text in text:
                    btn_y = (bbox[0][1] + bbox[2][1]) // 2
                    # 如果按钮的 Y 轴和标题接近（容差 100 像素）
                    if abs(btn_y - target_y) < 100:
                        center_x = int((bbox[0][0] + bbox[1][0]) // 2)
                        center_y = int(btn_y)
                        print(f"在任务 '{title_keyword}' 附近找到按钮 '{text}', 坐标: ({center_x}, {center_y})")
                        d.click(center_x, center_y)
                        return True
        
        # 如果没找到特定的标题+按钮对，尝试直接找全局第一个匹配的按钮（可选策略）
        time.sleep(1)
    return False

def handle_ad_playback(d):
    """处理视频广告播放及关闭"""
    print("等待广告播放中 (预设 35s)...")
    time.sleep(35)
    # 尝试多种关闭手段
    # 1. 常见的 ID/文本
    d(resourceIdMatches=r".*close.*|.*cancel.*").click_exists()
    d(textMatches=r"跳过|关闭|退出").click_exists()
    # 2. OCR 找 X 或关闭
    # find_and_click_ocr(d, "关闭", retry=1)
    d.press("back")
    time.sleep(2)

def qidian_main_tasks(d):
    print("准备开始福利中心任务...")
    
    # 1. 进入福利中心（自动完成签到）
    package, activity = get_current_app(d)
    if "QDBrowserActivity" not in activity:
        print("当前不在福利中心，尝试从主页进入...")
        start_app(d, QD_APP, init=True)
        time.sleep(6)
        d(resourceId="com.qidian.QDReader:id/mini_player_close").click_exists()
        me_tab = d(resourceId="com.qidian.QDReader:id/f6", text="我的")
        if me_tab.exists:
            me_tab.click()
            time.sleep(2)
            benefit_btn = d(text="福利中心")
            if benefit_btn.exists:
                benefit_btn.click()
                time.sleep(6)
    
    print("已进入福利中心，开始执行具体任务。")

    # 2. 定义要完成的具体任务关键词
    tasks = ["激励任务", "惊喜福利", "3个广告", "1个广告"]
    
    for task_name in tasks:
        # 每个任务尝试完成 1 次（如果有多次可以外层加循环）
        if find_text_and_click_button(d, task_name):
            print(f"已启动任务: {task_name}")
            handle_ad_playback(d)
            # 完成一个后稍微等一下加载回页面
            time.sleep(3)
        else:
            print(f"未找到任务或任务已完成: {task_name}")
            # 如果没找到，尝试向下滑动一点点再找
            d.swipe_ext("up", scale=0.3)
            time.sleep(2)

def main():
    try:
        device_id = select_device()
        d = u2.connect(device_id)
        print(f"已成功连接设备：{device_id}")
        
        # 执行起点综合任务
        qidian_main_tasks(d)
        
        print("起点读书所有任务执行完毕。")
    except Exception as e:
        print(f"运行出错: {e}")

if __name__ == "__main__":
    main()
