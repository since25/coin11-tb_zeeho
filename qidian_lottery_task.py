import time
import re
import random
import xml.etree.ElementTree as ET
import uiautomator2 as u2

from utils import easy_ocr, get_connected_devices, get_current_app, QD_APP
from qidianfuli_task import (
    choose_device_for_qidianfuli,
    bootstrap_to_welfare_center,
    recover_to_welfare_page,
    detect_countdown_seconds,
)

LOTTERY_ANCHOR_WORDS = ["做任务可抽奖"]
LOTTERY_ACTION_WORDS = ["去看看", "去完成", "立即抽奖", "去抽奖", "抽奖"]
LOTTERY_PLUS_ONE_WORDS = ["做任务抽奖机会+1", "抽奖机会+1", "任务抽奖机会+1", "机会+1"]
DRAW_BUTTON_WORDS = ["立即抽奖", "去抽奖", "抽奖", "开始抽奖"]


def normalize_text(text):
    return re.sub(r"\s+", "", (text or "").strip())


def is_lottery_entry_text(t):
    if "做任务可抽奖" in t:
        return True
    if re.search(r"抽奖机会[xX×]\d+", t):
        return True
    return False


def ocr_items(d):
    out = []
    for item in easy_ocr(d.screenshot(), return_info=True):
        if not isinstance(item, (tuple, list)) or len(item) != 3:
            continue
        bbox, text, conf = item
        t = normalize_text(text)
        if not t:
            continue
        try:
            x1 = float(bbox[0][0])
            y1 = float(bbox[0][1])
            x2 = float(bbox[2][0])
            y2 = float(bbox[2][1])
        except Exception:
            continue
        out.append(
            {
                "text": t,
                "raw_text": str(text),
                "conf": float(conf),
                "cx": int((x1 + x2) / 2),
                "cy": int((y1 + y2) / 2),
            }
        )
    return out


def detect_lottery_chances(items):
    for it in items:
        t = it["text"]
        m = re.search(r"抽奖机会[xX×](\d+)", t)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
    return None


def click_lottery_entry(d, max_rounds=6):
    for idx in range(max_rounds):
        items = ocr_items(d)
        w, h = d.window_size()
        anchors = []
        for it in items:
            t = it["text"]
            if not is_lottery_entry_text(t):
                continue
            if any(bad in t for bad in ["规则", "有效", "领取礼包", "仅当日"]):
                continue
            # 入口通常不在顶部规则区
            if it["cy"] < int(h * 0.22):
                continue
            anchors.append(it)
        if anchors:
            anchor = sorted(anchors, key=lambda x: (-x["conf"], abs(x["cx"] - int(w * 0.75)), x["cy"]))[0]
            action_candidates = []
            for it in items:
                if not any(k in it["text"] for k in LOTTERY_ACTION_WORDS):
                    continue
                if it["cx"] <= anchor["cx"]:
                    continue
                if abs(it["cy"] - anchor["cy"]) > 180:
                    continue
                action_candidates.append(it)

            if action_candidates:
                action = sorted(action_candidates, key=lambda x: (abs(x["cy"] - anchor["cy"]), -x["cx"]))[0]
                d.click(action["cx"], action["cy"])
                print(f"已点击抽奖入口动作: {action['raw_text']} @ ({action['cx']},{action['cy']})")
                return True

            d.click(anchor["cx"], anchor["cy"])
            print(f"已点击抽奖入口锚点: {anchor['raw_text']} @ ({anchor['cx']},{anchor['cy']})")
            return True

        print(f"第 {idx + 1}/{max_rounds} 轮未找到“做任务可抽奖”，下滑查找")
        d.swipe_ext("up", scale=0.22)
        time.sleep(1.0)
    return False


def click_text_by_keywords(d, keywords, prefer_top_right=False, prefer_bottom=False):
    items = ocr_items(d)
    if not items:
        return False
    w, h = d.window_size()
    cands = []
    for it in items:
        if not any(k in it["text"] for k in keywords):
            continue
        if prefer_top_right and not (it["cy"] < int(h * 0.35) and it["cx"] > int(w * 0.55)):
            continue
        cands.append(it)
    if not cands:
        return False
    if prefer_bottom:
        cands.sort(key=lambda x: (-x["cy"], abs(x["cx"] - w // 2)))
    else:
        cands.sort(key=lambda x: (-x["conf"], x["cy"]))
    target = cands[0]
    d.click(target["cx"], target["cy"])
    print(f"点击文案: {target['raw_text']} @ ({target['cx']},{target['cy']})")
    return True


def brief_browse(d, seconds=10):
    start = time.time()
    while time.time() - start < seconds:
        try:
            d.swipe_ext("up", scale=0.25)
        except Exception:
            pass
        time.sleep(random.uniform(1.2, 2.0))


def click_lottery_plus_one_task(d, max_rounds=6):
    for i in range(max_rounds):
        items = ocr_items(d)
        w, _ = d.window_size()
        chance_anchors = [it for it in items if re.search(r"抽奖机会[xX×]\d+", it["text"])]
        anchors = [it for it in items if any(k in it["text"] for k in LOTTERY_PLUS_ONE_WORDS)]
        if anchors:
            anchor = sorted(anchors, key=lambda x: (-x["conf"], x["cy"]))[0]
            actions = []
            for it in items:
                if not any(k in it["text"] for k in ["前往", "去完成", "去看看"]):
                    continue
                if it["cx"] <= anchor["cx"]:
                    continue
                if abs(it["cy"] - anchor["cy"]) > 180:
                    continue
                actions.append(it)
            if actions:
                t = sorted(actions, key=lambda x: (abs(x["cy"] - anchor["cy"]), -x["cx"]))[0]
                d.click(t["cx"], t["cy"])
                print(f"已点击“做任务抽奖机会+1”动作: {t['raw_text']} @ ({t['cx']},{t['cy']})")
                return True
            d.click(anchor["cx"], anchor["cy"])
            print(f"已点击“做任务抽奖机会+1”锚点: {anchor['raw_text']} @ ({anchor['cx']},{anchor['cy']})")
            return True

        # 兜底：在“抽奖机会xN”下方的任务卡里找前往/去完成，避免全局误点
        if chance_anchors:
            ch = sorted(chance_anchors, key=lambda x: (-x["conf"], x["cy"]))[0]
            row_actions = []
            for it in items:
                if not any(k in it["text"] for k in ["前往", "去完成", "去看看"]):
                    continue
                if it["cx"] < int(w * 0.55):
                    continue
                if not (ch["cy"] + 120 <= it["cy"] <= ch["cy"] + 1000):
                    continue
                row_actions.append(it)
            if row_actions:
                t = sorted(row_actions, key=lambda x: (x["cy"], -x["conf"]))[0]
                d.click(t["cx"], t["cy"])
                print(f"已点击抽奖任务受限兜底动作: {t['raw_text']} @ ({t['cx']},{t['cy']})")
                return True

        d.swipe_ext("up", scale=0.18)
        time.sleep(1.0)
        print(f"第 {i + 1}/{max_rounds} 轮未命中“做任务抽奖机会+1”")
    return False


def close_rewardvideo_layer_once(d):
    """更稳的广告关闭策略：过滤 systemui，优先广告层角点小控件。"""
    w, h = d.window_size()
    close_pattern = r"(close|cancel|exit|skip|dismiss|cross|关闭|跳过|退出|返回|x|×|✕)"
    selectors = [
        d(resourceIdMatches=rf".*{close_pattern}.*"),
        d(descriptionMatches=rf".*{close_pattern}.*"),
        d(textMatches=r"跳过|关闭|退出|返回|关闭广告"),
    ]
    for sel in selectors:
        try:
            if not sel.exists:
                continue
            info = sel.info or {}
            pkg = (info.get("packageName") or "")
            rid = (info.get("resourceName") or "")
            if "systemui" in pkg.lower() or "status_bar" in rid.lower():
                continue
            sel.click()
            time.sleep(0.5)
            return True
        except Exception:
            pass

    # 层级扫描角点小控件
    try:
        root = ET.fromstring(d.dump_hierarchy())
        nodes = []
        for n in root.iter("node"):
            bounds = n.get("bounds") or ""
            nums = re.findall(r"\d+", bounds)
            if len(nums) != 4:
                continue
            x1, y1, x2, y2 = map(int, nums)
            bw, bh = max(0, x2 - x1), max(0, y2 - y1)
            if bw <= 0 or bh <= 0:
                continue
            area = bw * bh
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            if cy > int(h * 0.28):
                continue
            if not (cx < int(w * 0.25) or cx > int(w * 0.75)):
                continue
            if area > int(w * h * 0.03):
                continue
            pkg = (n.get("package") or "").lower()
            if "systemui" in pkg:
                continue
            txt = " ".join(
                [
                    (n.get("text") or ""),
                    (n.get("content-desc") or ""),
                    (n.get("resource-id") or ""),
                    (n.get("class") or ""),
                ]
            ).lower()
            score = 10
            if re.search(close_pattern, txt, re.IGNORECASE):
                score += 100
            if "imagebutton" in txt or "button" in txt:
                score += 20
            if cx > int(w * 0.75):
                score += 10
            score -= int(area / 3000)
            nodes.append((score, cx, cy))
        nodes.sort(key=lambda x: x[0], reverse=True)
        for score, cx, cy in nodes[:4]:
            if score < 20:
                continue
            d.click(cx, cy)
            time.sleep(0.5)
            return True
    except Exception:
        pass

    # 盲点角点兜底
    for x, y in [(int(w * 0.95), int(h * 0.05)), (int(w * 0.90), int(h * 0.08)), (int(w * 0.06), int(h * 0.05))]:
        d.click(x, y)
        time.sleep(0.2)
    return False


def close_top_right_x(d, rounds=5):
    for i in range(rounds):
        close_rewardvideo_layer_once(d)
        time.sleep(0.6)
        if click_text_by_keywords(d, ["X", "×", "✕", "关闭", "跳过"], prefer_top_right=True):
            time.sleep(0.8)
        w, h = d.window_size()
        for x, y in [(int(w * 0.95), int(h * 0.05)), (int(w * 0.90), int(h * 0.08))]:
            d.click(x, y)
            time.sleep(0.2)
        pkg, act = get_current_app(d)
        if "RewardvideoPortraitADActivity" not in (act or ""):
            return True
        print(f"右上角关闭第 {i + 1}/{rounds} 轮后仍在广告页")
    return False


def run_lottery_ad_flow(d, timeout=140):
    print("进入抽奖专用广告流程")
    start = time.time()
    jumped = False
    while time.time() - start < timeout:
        pkg, act = get_current_app(d)
        act = act or ""
        if pkg is None:
            time.sleep(1.0)
            continue
        items = ocr_items(d)
        full_text = " ".join(i["text"] for i in items)

        # 外部应用落地页
        if pkg != "com.qidian.QDReader":
            print(f"检测到外部页面: {pkg}/{act}，浏览后返回")
            brief_browse(d, seconds=12)
            d.press("back")
            time.sleep(1.5)
            jumped = True
            continue

        # 起点内落地页
        if "ADActivity" in act and "RewardvideoPortraitADActivity" not in act:
            print(f"检测到起点内落地页: {act}，浏览后返回")
            brief_browse(d, seconds=12)
            d.press("back")
            time.sleep(1.3)
            jumped = True
            continue

        # 广告容器
        if "RewardvideoPortraitADActivity" in act:
            if not jumped:
                if click_text_by_keywords(d, ["查看详情", "了解详情", "点击去浏览", "立即下载", "去看看"], prefer_bottom=True):
                    print("已点击广告CTA，等待跳转")
                    time.sleep(2.0)
                    continue
            sec = detect_countdown_seconds(full_text)
            if sec is not None and sec > 4:
                wait_s = min(max(sec // 2, 2), 6)
                print(f"广告倒计时约 {sec}s，等待 {wait_s}s")
                time.sleep(wait_s)
                continue
            if close_top_right_x(d, rounds=2):
                print("广告页关闭成功")
                return True
            d.press("back")
            time.sleep(1.0)
            continue

        # 返回福利页/抽奖页
        if "QDBrowserActivity" in act:
            return True

        d.press("back")
        time.sleep(1.0)
    return False


def click_draw_button(d, max_rounds=5):
    banned_hint_words = ["机会", "赠送", "有效", "领取礼包", "仅当日", "规则"]
    for i in range(max_rounds):
        items = ocr_items(d)
        w, h = d.window_size()
        # 优先点击中间“抽奖”大按钮
        center_cands = []
        for it in items:
            t = it["text"]
            if t != "抽奖":
                continue
            if any(wd in t for wd in banned_hint_words):
                continue
            if it["cy"] < int(h * 0.28) or it["cy"] > int(h * 0.78):
                continue
            center_cands.append(it)
        if center_cands:
            center_cands.sort(key=lambda x: (abs(x["cx"] - w // 2), abs(x["cy"] - h // 2)))
            t = center_cands[0]
            d.click(t["cx"], t["cy"])
            print(f"已点击中间抽奖按钮: {t['raw_text']} @ ({t['cx']},{t['cy']})")
            return True
        # 优先“立即抽奖/去抽奖”
        for kw in ["立即抽奖", "去抽奖", "开始抽奖"]:
            cands = [it for it in items if kw in it["text"]]
            if cands:
                cands.sort(key=lambda x: (-x["conf"], -x["cy"]))
                t = cands[0]
                d.click(t["cx"], t["cy"])
                print(f"已点击抽奖按钮: {t['raw_text']} @ ({t['cx']},{t['cy']})")
                return True
        # 兜底：只接受短文案“抽奖”按钮，排除说明文字
        cands = []
        for it in items:
            t = it["text"]
            if "抽奖" not in t:
                continue
            if "可抽奖" in t or "做任务抽奖机会+1" in t:
                continue
            if any(w in t for w in banned_hint_words):
                continue
            if len(t) > 8:
                continue
            cands.append(it)
        if cands:
            cands.sort(key=lambda x: (-x["cy"], -x["conf"]))
            t = cands[0]
            d.click(t["cx"], t["cy"])
            print(f"已点击抽奖兜底按钮: {t['raw_text']} @ ({t['cx']},{t['cy']})")
            return True
        d.swipe_ext("down", scale=0.12)
        time.sleep(1.0)
        print(f"第 {i + 1}/{max_rounds} 轮未找到抽奖按钮")
    return False


def run_lottery_once(d):
    print("开始执行单独抽奖任务测试")

    if not bootstrap_to_welfare_center(d, max_rounds=6):
        raise RuntimeError("初始化失败：无法进入福利中心")

    if not click_lottery_entry(d, max_rounds=8):
        raise RuntimeError("未找到‘做任务可抽奖’入口")

    items0 = ocr_items(d)
    chances0 = detect_lottery_chances(items0)
    print(f"当前抽奖机会: {chances0 if chances0 is not None else 'unknown'}")
    if chances0 == 0:
        print("当前无抽奖机会，关闭起点并退出脚本")
        try:
            d.app_stop(QD_APP)
        except Exception:
            pass
        print("=== 抽奖任务测试结果 ===")
        print("广告流程结果: skipped(无抽奖机会)")
        print("广告页右上角退出结果: skipped")
        print("回到福利页结果: True")
        print("点击抽奖按钮结果: skipped")
        print("检测到抽奖相关文案: True")
        return

    if chances0 is not None and chances0 > 0:
        draw_ok = click_draw_button(d, max_rounds=5)
        items = ocr_items(d)
        all_text = " ".join(i["text"] for i in items)
        lottery_hint = any(k in all_text for k in ["抽奖", "次数", "抽奖机会", "可抽奖"])
        print("=== 抽奖任务测试结果 ===")
        print("广告流程结果: skipped(已有抽奖机会)")
        print("广告页右上角退出结果: skipped")
        print("回到福利页结果: True")
        print(f"点击抽奖按钮结果: {draw_ok}")
        print(f"检测到抽奖相关文案: {lottery_hint}")
        return

    time.sleep(2.0)
    if not click_lottery_plus_one_task(d, max_rounds=8):
        raise RuntimeError("未找到‘做任务抽奖机会+1’按钮")

    flow_ok = run_lottery_ad_flow(d, timeout=140)
    close_ok = close_top_right_x(d, rounds=6)
    back_ok = recover_to_welfare_page(d, max_rounds=12)

    # 回到福利页后再次进入抽奖区并点击抽奖按钮
    if not click_lottery_entry(d, max_rounds=4):
        print("未重新命中抽奖入口，直接尝试抽奖按钮")
    draw_ok = click_draw_button(d, max_rounds=5)

    items = ocr_items(d)
    all_text = " ".join(i["text"] for i in items)
    lottery_hint = any(k in all_text for k in ["抽奖", "次数", "抽奖机会", "可抽奖"])

    print("=== 抽奖任务测试结果 ===")
    print(f"广告流程结果: {flow_ok}")
    print(f"广告页右上角退出结果: {close_ok}")
    print(f"回到福利页结果: {back_ok}")
    print(f"点击抽奖按钮结果: {draw_ok}")
    print(f"检测到抽奖相关文案: {lottery_hint}")


def main():
    device_id = choose_device_for_qidianfuli()
    d = u2.connect(device_id)
    run_lottery_once(d)


if __name__ == "__main__":
    main()
