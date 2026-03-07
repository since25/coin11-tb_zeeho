import uiautomator2 as u2
import time
from utils import select_device, start_app, QD_APP, easy_ocr, get_current_app, get_connected_devices
from PIL import Image
import os
import re
import xml.etree.ElementTree as ET

AD_CTA_POINTS = [(540, 2270), (540, 2201), (540, 1691), (540, 2491)]
PREFERRED_DEVICE = "192.168.70.154:39931"

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

def has_reward_overlay(d):
    """是否仍存在奖励浮窗/遮罩。"""
    txt = easy_ocr(d.screenshot())
    # 收紧判定：避免把任务页“得奖励”正文误识别为浮窗
    has_ack = ("知道了" in txt) or ("我知道了" in txt)
    has_reward_title = any(w in txt for w in ["恭喜", "已获得", "领取成功", "奖励已发放", "奖励到账"])
    return has_ack and has_reward_title

def click_ack_popup_button(d, retry=3):
    """
    严格点击奖励浮窗里的“知道了”按钮，避免误点到列表正文。
    规则：文本必须是短按钮文案，且位于屏幕下半区。
    """
    w, h = d.window_size()
    valid_texts = {"知道了", "我知道了", "确定", "收下"}
    for _ in range(retry):
        ocr_res = easy_ocr(d.screenshot(), return_info=True)
        candidates = []
        for (bbox, text, prob) in ocr_res:
            t = (text or "").strip()
            if not t:
                continue
            # 严格匹配短按钮文本，避免 "完成1个广告任务得奖知道了" 这种长串误命中
            if (t in valid_texts) or (("知道了" in t) and len(t) <= 6):
                cx = int((bbox[0][0] + bbox[1][0]) // 2)
                cy = int((bbox[0][1] + bbox[2][1]) // 2)
                bw = abs(int(bbox[1][0] - bbox[0][0]))
                bh = abs(int(bbox[2][1] - bbox[0][1]))
                # 奖励按钮通常在中下部，且尺寸不像正文那样很长
                if cy > h * 0.45 and cy < h * 0.95 and bw < w * 0.55 and bh < h * 0.15:
                    candidates.append((cx, cy, bw * bh, t))
        if candidates:
            # 优先点更像按钮（面积更小、离屏幕中线更近）
            candidates.sort(key=lambda x: (abs(x[0] - w // 2), x[2]))
            cx, cy, _, t = candidates[0]
            d.click(cx, cy)
            time.sleep(1.2)
            if not has_reward_overlay(d):
                print(f"已处理奖励弹窗按钮: {t} @ ({cx}, {cy})")
                return True
            print(f"点击了疑似按钮但浮窗仍在: {t} @ ({cx}, {cy})，继续重试")
        else:
            # 兜底：尝试点击底部中间常见确认位
            d.click(w // 2, int(h * 0.82))
            time.sleep(1.0)
            if not has_reward_overlay(d):
                print("底部中间兜底点击后，奖励浮窗已消失。")
                return True
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
    返回值:
      True  - 已触发一个高置信度关闭动作
      False - 没找到可靠关闭点，交由上层执行 back 兜底
    """
    print("尝试寻找广告关闭按钮...")
    w, h = d.window_size()
    if ocr_contains(d, ["恭喜"]):
        print("检测到‘恭喜’，该层可能禁用 back，优先强制查找并点击 X...")
        for _ in range(2):
            for (cx, cy) in [(40, 70), (80, 110), (120, 90), (1040, 70), (1000, 110), (960, 90)]:
                d.click(cx, cy)
                time.sleep(0.25)
            if not ocr_contains(d, ["恭喜"]):
                print("‘恭喜’提示已消失，视为关闭成功。")
                return True

    close_pattern = r"(close|cancel|exit|skip|dismiss|cross|关闭|跳过|退出|返回|x|×|✕)"

    # 策略 1: 常见关键字（优先，避免先误点广告素材）
    close_selectors = [
        d(resourceIdMatches=rf".*{close_pattern}.*"),
        d(descriptionMatches=rf".*{close_pattern}.*"),
        d(textMatches=r"跳过|关闭|退出|返回|关闭广告"),
    ]
    for sel in close_selectors:
        if sel.exists:
            print(f"选择器命中: {sel.info.get('resourceName', 'Unknown')}")
            sel.click()
            return True

    # 策略 2: 扫描 UI 层次结构，优先高置信度小按钮（右上/左上）
    print("正在分析 UI 层次结构寻找边角关闭按钮...")
    ui_hierarchy = d.dump_hierarchy()
    root = ET.fromstring(ui_hierarchy)

    potential_nodes = []
    for node in root.iter("node"):
        clickable = node.get("clickable") == "true"
        cls = (node.get("class") or "").lower()
        if (not clickable) and ("image" not in cls) and ("button" not in cls):
            continue

        bounds = node.get("bounds") or ""
        nums = re.findall(r"\d+", bounds)
        if len(nums) != 4:
            continue
        x1, y1, x2, y2 = map(int, nums)
        bw, bh = max(0, x2 - x1), max(0, y2 - y1)
        if bw <= 0 or bh <= 0:
            continue

        area = bw * bh
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        is_top = cy < h * 0.28
        is_edge = (cx < w * 0.25) or (cx > w * 0.75)
        if not (is_top and is_edge):
            continue

        # 过滤明显不是关闭按钮的大区域，避免误点广告主素材
        if area > (w * h * 0.025):
            continue

        text_parts = [
            (node.get("text") or "").strip(),
            (node.get("content-desc") or "").strip(),
            (node.get("resource-id") or "").strip(),
        ]
        node_text = " ".join([t for t in text_parts if t]).lower()

        score = 0
        if re.search(close_pattern, node_text, re.IGNORECASE):
            score += 120
        if "imagebutton" in cls or "button" in cls:
            score += 20
        elif "imageview" in cls:
            score += 10
        if cx > w * 0.75:
            score += 15
        elif cx < w * 0.25:
            score += 10
        score -= int(area / 3000)

        potential_nodes.append({
            "x": cx,
            "y": cy,
            "score": score,
            "area": area,
            "text": node_text[:80],
            "class": node.get("class") or "",
        })

    potential_nodes.sort(key=lambda n: n["score"], reverse=True)
    for node in potential_nodes[:5]:
        # 仅点击有足够置信度的节点
        if node["score"] < 35:
            continue
        print(
            f"层级识别点击候选: score={node['score']} class={node['class']} "
            f"area={node['area']} @ ({node['x']}, {node['y']}) text={node['text']}"
        )
        d.click(node["x"], node["y"])
        time.sleep(0.8)
        return True

    # 策略 3: OCR
    if find_and_click_ocr(d, "×", retry=1): return True
    if find_and_click_ocr(d, "✕", retry=1): return True
    if find_and_click_ocr(d, "X", retry=1): return True
    if find_and_click_ocr(d, "关闭", retry=1): return True
    if find_and_click_ocr(d, "跳过", retry=1): return True
    if find_and_click_ocr(d, "返回", retry=1): return True
    
    # 策略 4: 盲点 (左右上角都尝试)，但不判定为成功，让上层继续 back 兜底
    print("层级和 OCR 均失败，执行盲点点击并交由 back 兜底...")
    盲触点 = [
        (60, 60), (100, 100), (60, 150),
        (w - 60, 60), (w - 100, 100), (w - 60, 150),
    ]
    for (cx, cy) in 盲触点:
        d.click(cx, cy)
        time.sleep(0.25)
    if ocr_contains(d, ["恭喜"]):
        print("盲点后仍检测到‘恭喜’，继续优先点击左上/右上 X，不执行 back。")
        for (cx, cy) in [(40, 70), (80, 110), (1040, 70), (1000, 110)]:
            d.click(cx, cy)
            time.sleep(0.2)
    
    # 调试记录：如果都失败了，保存一份 dump 以便分析
    if not any(sel.exists for sel in close_selectors):
        with open("ad_error_dump.xml", "w", encoding="utf-8") as f:
            f.write(ui_hierarchy)
        print("已保存当前 UI 布局到 ad_error_dump.xml 供后续分析。")
        
    return False

def wait_and_browse_external_ad(d, min_watch_seconds=22, max_wait_jump_seconds=10):
    """
    点击“了解详情”后，等待广告真正跳转并模拟浏览。
    目的：避免只看了页面内倒计时，外部广告计时不够导致奖励未发放。
    """
    print("等待广告跳转到落地页...")
    jumped = False
    for i in range(max_wait_jump_seconds):
        pkg, act = get_current_app(d)
        act = act or ""
        if pkg != QD_APP or ("RewardvideoPortraitADActivity" not in act):
            print(f"检测到已跳转: {pkg}/{act}")
            jumped = True
            break
        time.sleep(1)

    if not jumped:
        print("未检测到外部跳转，跳过外部浏览阶段。")
        return

    print(f"开始模拟浏览，至少停留 {min_watch_seconds}s ...")
    start = time.time()
    while time.time() - start < min_watch_seconds:
        d.swipe_ext("up", scale=0.35)
        time.sleep(2)

    print("外部浏览时长满足，尝试返回广告容器...")
    for _ in range(3):
        pkg, act = get_current_app(d)
        act = act or ""
        if pkg == QD_APP and "RewardvideoPortraitADActivity" in act:
            print("已回到广告容器。")
            return
        d.press("back")
        time.sleep(1.5)

def tap_ad_cta_and_wait_jump(d, jump_wait_seconds=6):
    """
    点击广告 CTA（优先 OCR，失败则用实测坐标），并等待是否成功跳转。
    """
    for keyword in ["继续看", "继续观看", "了解详情", "了解更多", "去看看"]:
        if find_and_click_ocr(d, keyword, retry=1):
            for _ in range(jump_wait_seconds):
                pkg, act = get_current_app(d)
                act = act or ""
                if pkg != QD_APP or ("RewardvideoPortraitADActivity" not in act):
                    print(f"CTA(OCR) 点击后已跳转: {pkg}/{act}")
                    return True
                time.sleep(1)

    print("OCR 未命中 CTA，尝试固定坐标点击...")
    for (x, y) in AD_CTA_POINTS:
        d.click(x, y)
        time.sleep(1.8)
        pkg, act = get_current_app(d)
        act = act or ""
        if pkg != QD_APP or ("RewardvideoPortraitADActivity" not in act):
            print(f"CTA(坐标) 点击后已跳转: {pkg}/{act}")
            return True
    return False

def handle_continue_watch_prompt(d, extra_watch_seconds=12):
    """
    处理“继续看X秒可获得奖励”类提示。
    """
    continue_keywords = ["继续看", "继续观看", "再看", "可获得奖励", "获得奖励", "继续浏览"]
    screenshot = d.screenshot()
    txt = easy_ocr(screenshot)
    if any(k in txt for k in continue_keywords):
        print("检测到继续观看提示，尝试再次点击‘了解详情/继续看’...")
        if tap_ad_cta_and_wait_jump(d, jump_wait_seconds=6):
            wait_and_browse_external_ad(d, min_watch_seconds=extra_watch_seconds, max_wait_jump_seconds=6)
            return True
    return False

def handle_ad_playback(d):
    print("进入广告交互流程...")
    time.sleep(3)
    d.swipe_ext("up", scale=0.2)
    time.sleep(1)
    
    if tap_ad_cta_and_wait_jump(d, jump_wait_seconds=10):
        print("启动任务倒计时：已点击‘了解详情’")
        wait_and_browse_external_ad(d, min_watch_seconds=22, max_wait_jump_seconds=10)
    
    print("循环监测奖励发放状态（含自动补看）...")
    reward_confirmed = False
    for round_idx in range(4):
        print(f"奖励检测轮次: {round_idx + 1}/4")
        for attempt in range(6): # 每轮最多 30s
            screenshot = d.screenshot()
            txt = easy_ocr(screenshot)
            if any(keyword in txt for keyword in ["恭喜", "已发放", "奖励到账", "任务完成"]):
                print("奖励确认到账！")
                reward_confirmed = True
                break
            print(f"监测中... {(attempt + 1) * 5}/30s")
            time.sleep(5)
        if reward_confirmed:
            break

        # 未到账则先处理“继续看”提示，没提示也主动再补看一次
        if handle_continue_watch_prompt(d, extra_watch_seconds=12):
            time.sleep(2)
            continue
        print("未识别到继续看提示，主动触发一次补看...")
        if tap_ad_cta_and_wait_jump(d, jump_wait_seconds=6):
            wait_and_browse_external_ad(d, min_watch_seconds=12, max_wait_jump_seconds=6)
            time.sleep(2)
    
    # 点击关闭 + back 兜底
    closed = find_close_button(d)
    time.sleep(2)

    for i in range(3):
        if find_and_click_ocr(d, "知道了", retry=1):
            print("已处理‘知道了’弹窗。")
            return
        if not closed or i > 0:
            print(f"第 {i + 1} 次尝试物理后退...")
            d.press("back")
            time.sleep(1.2)
        closed = False

def reward_keyword_detected(d):
    """快速检测是否出现奖励到账相关关键词。"""
    screenshot = d.screenshot()
    txt = easy_ocr(screenshot)
    reward_keywords = ["恭喜", "获得", "已发放", "奖励到账", "任务完成", "可获得奖励"]
    return any(k in txt for k in reward_keywords)

def ocr_contains(d, keywords):
    screenshot = d.screenshot()
    txt = easy_ocr(screenshot)
    return any(k in txt for k in keywords)

def page_signature(d):
    """轻量页面签名，用于判断点击/返回是否真的生效。"""
    pkg, activity = get_current_app(d)
    activity = activity or ""
    txt = easy_ocr(d.screenshot())
    txt = txt[:120]
    return f"{pkg}|{activity}|{txt}"

def is_in_welfare_center_page(d):
    """判断是否回到福利中心任务页。"""
    try:
        _, activity = get_current_app(d)
        activity = activity or ""
    except Exception:
        activity = ""
    screenshot = d.screenshot()
    txt = easy_ocr(screenshot)
    # 仍存在奖励浮窗时，不能判定已回到任务页
    if any(k in txt for k in ["恭喜", "知道了", "已获得", "奖励已发放"]):
        return False
    in_browser = ("QDBrowserActivity" in activity) or ("Browser" in activity)
    has_welfare_keywords = any(k in txt for k in ["福利中心", "去完成", "激励任务", "惊喜福利", "广告任务"])
    return in_browser and has_welfare_keywords

def is_in_main_me_page(d):
    """是否处于起点主应用的“我”页。"""
    try:
        pkg, activity = get_current_app(d)
        activity = activity or ""
    except Exception:
        pkg, activity = None, ""
    if pkg != QD_APP:
        return False
    if "MainGroupActivity" not in activity:
        return False
    return ocr_contains(d, ["我的账户", "福利中心", "我发布的", "帮助与客服"])

def ensure_back_to_welfare_from_main(d):
    """如果误退回主首页/我页，重新进入福利中心。"""
    if is_in_welfare_center_page(d):
        return True
    if is_in_main_me_page(d):
        print("检测到已回到“我”页，重新进入福利中心...")
        return enter_welfare_center(d)
    return False

def recover_to_welfare_center(d, retry_rounds=8):
    """
    从广告完成后的中间页面，回到福利中心任务页。
    处理顺序：知道了弹窗 -> 右上角叉号 -> back 兜底。
    """
    print("开始执行收尾回退：返回福利中心任务页...")
    w, h = d.window_size()
    close_points = [
        # 左上角优先（你的现场反馈）
        (40, 70), (80, 110), (120, 90), (40, 150), (80, 180),
        (w - 40, 70), (w - 80, 110), (w - 120, 90), (w - 40, 150), (w - 80, 180),
    ]
    for i in range(retry_rounds):
        # 先消除奖励浮窗，避免“半透明背景 + OCR”误判已回到任务页
        if has_reward_overlay(d):
            print("检测到奖励浮窗，优先处理‘知道了/确定’按钮...")
            click_ack_popup_button(d, retry=2)

        if is_in_welfare_center_page(d):
            print("已回到福利中心任务页。")
            return True
        if ensure_back_to_welfare_from_main(d):
            return True

        if ocr_contains(d, ["恭喜"]):
            print("检测到‘恭喜’，该层 back 可能无效，改为强制点 X（左上优先）...")
            sig_before = page_signature(d)
            for (x, y) in close_points:
                d.click(x, y)
                time.sleep(0.25)
                if is_in_welfare_center_page(d):
                    print("点击 X 后已回到福利中心任务页。")
                    return True
                if ensure_back_to_welfare_from_main(d):
                    return True
                if not ocr_contains(d, ["恭喜"]):
                    print("‘恭喜’提示已消失，继续收尾流程。")
                    break
            sig_after = page_signature(d)
            if sig_after != sig_before:
                print("页面已变化，继续下一轮收尾判断。")
                continue

        # 1) 优先处理弹窗确认（严格按钮逻辑）
        if click_ack_popup_button(d, retry=1):
            time.sleep(1.2)
            continue

        # 2) 尝试右上角关闭叉号
        for (x, y) in close_points:
            d.click(x, y)
            time.sleep(0.35)
        time.sleep(0.8)
        if is_in_welfare_center_page(d):
            print("点击右上角后已回到福利中心任务页。")
            return True

        # 3) back 兜底
        pkg, activity = get_current_app(d)
        activity = activity or ""
        if pkg == QD_APP and ("RewardvideoPortraitADActivity" in activity or "QDBrowserActivity" in activity):
            print(f"收尾回退第 {i + 1}/{retry_rounds} 轮：执行受控 back")
            d.press("back")
            time.sleep(1.2)
        else:
            print(f"收尾回退第 {i + 1}/{retry_rounds} 轮：当前非广告容器，跳过 back 防止过退")

    print("收尾回退未确认回到福利中心，继续按当前页面流程向下执行。")
    return False

def enter_welfare_center(d):
    """
    从起点主界面进入福利中心，包含 OCR 兜底。
    """
    # 1) 尝试进入“我的”
    me_tab = d(resourceIdMatches=r".*tab_me.*|.*f6.*", text="我的")
    me_tab_alt = d(resourceId="com.qidian.QDReader:id/view_tab_title_title", text="我")
    me_text_alt = d(text="我")
    if me_tab.exists:
        print("点击进入“我的”页面...")
        me_tab.click()
    elif me_tab_alt.exists:
        print("点击进入“我”页面...")
        me_tab_alt.click()
    elif me_text_alt.exists:
        print("点击进入“我”页面（文本选择器）...")
        me_text_alt.click()
    else:
        print("未通过 selector 找到‘我的’，尝试 OCR/坐标兜底...")
        if not (find_and_click_ocr(d, "我的", retry=1, exact=False) or find_and_click_ocr(d, "我", retry=1, exact=False)):
            w, h = d.window_size()
            d.click(int(w * 0.9), int(h - 100))
    time.sleep(3)

    # 2) 查找“福利中心”
    for i in range(6):
        benefit_btn = d(text="福利中心")
        # 文本节点可能不可点击，优先点其父容器
        benefit_parent = d.xpath('//*[@text="福利中心"]/..')
        benefit_grand = d.xpath('//*[@text="福利中心"]/../..')
        if benefit_parent.exists:
            print("找到福利中心父容器，正在进入...")
            benefit_parent.click()
            time.sleep(8)
            return True
        if benefit_grand.exists:
            print("找到福利中心祖先容器，正在进入...")
            benefit_grand.click()
            time.sleep(8)
            return True
        if benefit_btn.exists:
            print("找到福利中心文本节点，正在进入...")
            benefit_btn.click()
            time.sleep(8)
            return True
        if find_and_click_ocr(d, "福利中心", retry=1, exact=False):
            print("OCR 命中福利中心，正在进入...")
            time.sleep(8)
            return True
        print(f"第 {i + 1}/6 次未找到福利中心，继续小幅滑动查找...")
        d.swipe_ext("up", scale=0.22)
        time.sleep(1.2)
    return False

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
        if not enter_welfare_center(d):
            print("致命错误：无法在‘我的’页面定位到‘福利中心’入口")
            return
    
    # 确认进入后，开始任务（只做 2 次广告测试）
    print("当前已确保在福利中心，准备执行具体任务...")
    tasks = ["3个广告", "1个广告", "惊喜福利", "激励任务"]
    completed_ads = 0
    max_ad_tests = 2
    scroll_rounds = 0
    max_scroll_rounds = 10
    while completed_ads < max_ad_tests and scroll_rounds < max_scroll_rounds:
        found_this_round = False
        for task_name in tasks:
            # 每个任务尝试 1 次，避免重复OCR耗时过长
            if find_text_and_click_button(d, task_name, retry=1):
                handle_ad_playback(d)
                recover_to_welfare_center(d, retry_rounds=8)
                if reward_keyword_detected(d):
                    print("返回任务页后检测到奖励关键词。")
                else:
                    print("返回任务页后未检测到奖励关键词。")
                print(f"任务阶段结束: {task_name}")
                time.sleep(3)
                found_this_round = True
                completed_ads += 1
                break

        if completed_ads >= max_ad_tests:
            break

        if not found_this_round:
            scroll_rounds += 1
            print(f"未找到可执行任务，滚动查找下一屏... ({scroll_rounds}/{max_scroll_rounds})")
            d.swipe_ext("up", scale=0.32)
            time.sleep(2)

    print(f"广告测试完成数: {completed_ads}/{max_ad_tests}")

def choose_device_for_qidian(preferred_device=PREFERRED_DEVICE):
    """
    设备选择规则：
    1) 仅 1 台设备：自动选择
    2) 多台设备：优先选择 preferred_device
    3) 优先设备不在列表：回退到原交互式选择
    """
    devices = get_connected_devices()
    if not devices:
        raise Exception("未检测到任何连接的安卓设备")
    if len(devices) == 1:
        print(f"仅检测到 1 台设备，自动选择: {devices[0]}")
        return devices[0]
    if preferred_device in devices:
        print(f"检测到多台设备，优先选择: {preferred_device}")
        return preferred_device
    print("检测到多台设备，但优先设备不在列表，切换为手动选择。")
    return select_device()

def main():
    try:
        device_id = choose_device_for_qidian()
        d = u2.connect(device_id)
        # 先确保起点读书在前台，避免在其他应用页面误执行导航逻辑
        start_app(d, QD_APP, init=False)
        time.sleep(3)
        qidian_main_tasks(d)
        print("起点福利中心任务全部执行完成。")
    except Exception as e:
        print(f"脚本执行中断: {e}")

if __name__ == "__main__":
    main()
