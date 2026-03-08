import time
import uiautomator2 as u2
from utils import select_device, start_app, ZEEHO_APP, get_current_app

AUTO_STOP_APP = False


def _in_zeeho(d):
    pkg, _ = get_current_app(d)
    return pkg == ZEEHO_APP


def _ensure_zeeho_foreground(d):
    if _in_zeeho(d):
        return True
    print("当前不在极核前台，尝试拉起应用...")
    start_app(d, ZEEHO_APP, init=False)
    time.sleep(2)
    return _in_zeeho(d)


def _click_first(selectors, sleep_after=1.2):
    for sel in selectors:
        try:
            if sel.exists:
                sel.click()
                time.sleep(sleep_after)
                return True
        except Exception:
            continue
    return False


def _has_bottom_tabs(d):
    return (
        d(resourceId="com.cfmoto:id/tv_comm").exists
        or d(text="极客").exists
        or d(resourceId="com.cfmoto:id/tv_me").exists
        or d(text="我的").exists
    )


def _back_to_main_tabs(d, max_back=3):
    if _has_bottom_tabs(d):
        return True
    for i in range(max_back):
        if not _in_zeeho(d):
            print("返回时检测到已离开极核，停止回退。")
            return False
        print(f"签到后返回主页面，第 {i + 1}/{max_back} 次 back...")
        d.press("back")
        time.sleep(1.4)
        if _has_bottom_tabs(d):
            print("已返回包含底部 tab 的主页面。")
            return True
    return _has_bottom_tabs(d)

def sign_in(d):
    print("准备进入【我的】页面进行签到...")
    if not _ensure_zeeho_foreground(d):
        print("无法切回极核前台，签到流程终止。")
        return False

    # 点击底部“我的”
    if not _click_first([
        d(resourceId="com.cfmoto:id/tv_me", text="我的"),
        d(resourceId="com.cfmoto:id/tv_me"),
        d(text="我的"),
        d(description="我的"),
    ], sleep_after=2.5):
        print("未找到‘我的’入口。")
        return False
    
    # 查找签到文本
    sign_text = d(resourceId="com.cfmoto:id/tv_sign_in")
    if sign_text.exists or d(textContains="签到").exists:
        text = ""
        try:
            if sign_text.exists:
                text = sign_text.get_text() or ""
        except Exception:
            text = ""
        print(f"当前签到状态: {text or '未读取到状态文本，尝试直接点击'}")
        if "已签到" not in text:
            print("执行签到...")
            clicked = _click_first([
                d(resourceId="com.cfmoto:id/rl_sign_in"),
                d(resourceId="com.cfmoto:id/tv_sign_in"),
                d(text="签到"),
                d(textContains="签到"),
            ], sleep_after=2.2)
            if clicked:
                print("签到点击已执行。")
                if not _back_to_main_tabs(d, max_back=3):
                    print("签到后未能确认回到主页面，后续可能找不到‘极客’入口。")
            else:
                print("未找到可点击的签到控件。")
                return False
        else:
            print("今日已签到，跳过。")
    else:
        print("未找到签到入口，请检查UI层级是否已更改。")
        return False
    return True

def auto_like(d, like_count=2):
    print(f"准备进入【极客】社区页面连续点赞 {like_count} 次...")
    if not _ensure_zeeho_foreground(d):
        print("无法切回极核前台，点赞流程终止。")
        return False

    # 点击底部“极客”
    if not _click_first([
        d(resourceId="com.cfmoto:id/tv_comm", text="极客"),
        d(resourceId="com.cfmoto:id/tv_comm"),
        d(text="极客"),
        d(description="极客"),
    ], sleep_after=3.2):
        print("未找到社区入口。")
        return False

    # 切换到【最新】或者默认第一个Tab
    # 这里可以选择滑动信息流
    print("开始在信息流中点赞...")
    liked = 0
    max_swipes = 30
    swipes = 0
    
    while liked < like_count and swipes < max_swipes:
        # 获取当前屏幕上的所有点赞按钮的容器
        like_containers = d(resourceId="com.cfmoto:id/rl_like")
        
        for i in range(len(like_containers)):
            if liked >= like_count:
                break
            try:
                container = like_containers[i]
                bounds = container.info['bounds']
                # 简单防重：Y坐标必须在屏幕中间有效区域（防止点到被遮挡的半个按钮）
                if bounds['top'] > 300 and bounds['bottom'] < 2400:
                    # 点击点赞
                    print(f"点击点赞...")
                    container.click()
                    time.sleep(1.5)
                    liked += 1
            except Exception as e:
                print(f"点赞时出现异常: {e}")
        
        # 滑动屏幕看下一批
        print("向下滑动...")
        d.swipe_ext("up", scale=0.6)
        time.sleep(2)
        swipes += 1

    print(f"点赞任务结束，共点赞 {liked} 次。")
    return liked > 0

def main():
    selected_device = select_device()
    d = u2.connect(selected_device)
    print(f"已成功连接设备：{selected_device}")
    
    # 极核APP启动
    start_app(d, ZEEHO_APP, init=True)
    time.sleep(8)  # 等待广告播放完毕和主页加载
    
    # 执行签到
    sign_ok = sign_in(d)
    
    # 执行点赞
    like_ok = auto_like(d, like_count=2)
    
    print(f"极核(Zeeho)任务结束。签到状态: {sign_ok}, 点赞状态: {like_ok}")
    if AUTO_STOP_APP:
        d.app_stop(ZEEHO_APP)
    else:
        print("保留极核前台（AUTO_STOP_APP=False），便于排查。")

if __name__ == "__main__":
    main()
