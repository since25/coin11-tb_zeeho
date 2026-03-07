import uiautomator2 as u2
import time
from utils import select_device, start_app, QD_APP, easy_ocr, get_current_app
from PIL import Image

def find_and_click_ocr(d, target_text, retry=3):
    """使用 OCR 查找并点击特定文字"""
    for i in range(retry):
        print(f"正在尝试通过 OCR 查找: {target_text} (第 {i+1} 次)")
        screenshot = d.screenshot()
        # 使用 utils 中改进后的 easy_ocr 获取带坐标的原始信息
        ocr_res = easy_ocr(screenshot, return_info=True)
        
        for (bbox, text, prob) in ocr_res:
            # 兼容识别结果，处理一些常见的识别误差
            if target_text == text or (target_text in text and len(text) < len(target_text) + 2):
                # bbox: [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
                # 转换为原生 int 防止 json 序列化错误 (int64 is not JSON serializable)
                center_x = int((bbox[0][0] + bbox[1][0]) // 2)
                center_y = int((bbox[0][1] + bbox[2][1]) // 2)
                print(f"找到目标 '{text}', 坐标: ({center_x}, {center_y})")
                d.click(center_x, center_y)
                return True
        time.sleep(2)
    return False

def qidian_sign_in(d):
    print("进入起点读书签到流程...")
    # 1. 确保在“福利中心”
    package, activity = get_current_app(d)
    if "QDBrowserActivity" not in activity and "Benefit" not in activity:
        print("当前不在福利中心，尝试从主页进入...")
        start_app(d, QD_APP, init=True)
        time.sleep(5)
        # 关掉弹窗
        d(resourceId="com.qidian.QDReader:id/mini_player_close").click_exists()
        me_tab = d(resourceId="com.qidian.QDReader:id/f6", text="我的")
        if me_tab.exists:
            me_tab.click()
            time.sleep(2)
            benefit_btn = d(text="福利中心")
            if benefit_btn.exists:
                benefit_btn.click()
                time.sleep(5)
            else:
                print("未找到‘福利中心’入口")
                return

    # 2. 在福利中心查找并点击“签到”
    # 注意：起点有的页面是“签到”，有的是“今日签到”，有的是“签到领币”
    if find_and_click_ocr(d, "签到"):
        print("签到按钮已点击")
    else:
        print("未发现签到按钮，可能已签到")

def qidian_video_task(d):
    print("开始起点读书看视频任务...")
    # 在福利中心页面查找“看视频领币”或“看视频得福利”
    if find_and_click_ocr(d, "看视频"):
        print("已点击视频任务，进入视频播放中...")
        # 等待视频播放完成 (通常 30s + 几秒缓冲)
        time.sleep(35)
        # 尝试点击关闭按钮
        d(resourceIdMatches=r".*close.*|.*cancel.*").click_exists()
        find_and_click_ocr(d, "关闭")
        d.press("back")
        print("视频任务处理尝试结束")
    else:
        print("未发现视频任务按钮")

def main():
    try:
        device_id = select_device()
        d = u2.connect(device_id)
        print(f"已成功连接设备：{device_id}")
        
        # 执行起点任务
        qidian_sign_in(d)
        time.sleep(2)
        qidian_video_task(d)
        
        print("起点读书任务执行完毕。")
    except Exception as e:
        print(f"运行出错: {e}")

if __name__ == "__main__":
    main()
