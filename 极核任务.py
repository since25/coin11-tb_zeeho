import time
import uiautomator2 as u2
from utils import select_device, start_app, ZEEHO_APP

def sign_in(d):
    print("准备进入【我的】页面进行签到...")
    # 点击底部“我的”
    me_tab = d(resourceId="com.cfmoto:id/tv_me", text="我的")
    if me_tab.exists:
        me_tab.click()
        time.sleep(3)
    
    # 查找签到文本
    sign_text = d(resourceId="com.cfmoto:id/tv_sign_in")
    if sign_text.exists:
        text = sign_text.get_text()
        print(f"当前签到状态: {text}")
        if "已签到" not in text:
            print("执行签到...")
            d(resourceId="com.cfmoto:id/rl_sign_in").click()
            time.sleep(3)
            print("签到完成！")
        else:
            print("今日已签到，跳过。")
    else:
        print("未找到签到入口，请检查UI层级是否已更改。")

def auto_like(d, like_count=2):
    print(f"准备进入【极客】社区页面连续点赞 {like_count} 次...")
    # 点击底部“极客”
    comm_tab = d(resourceId="com.cfmoto:id/tv_comm", text="极客")
    if comm_tab.exists:
        comm_tab.click()
        time.sleep(4)
    else:
        print("未找到社区入口。")
        return

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

def main():
    selected_device = select_device()
    d = u2.connect(selected_device)
    print(f"已成功连接设备：{selected_device}")
    
    # 极核APP启动
    start_app(d, ZEEHO_APP, init=True)
    time.sleep(8)  # 等待广告播放完毕和主页加载
    
    # 执行签到
    sign_in(d)
    
    # 执行点赞
    auto_like(d, like_count=2)
    
    print("极核(Zeeho)所有任务已执行完毕。")
    d.app_stop(ZEEHO_APP)

if __name__ == "__main__":
    main()
