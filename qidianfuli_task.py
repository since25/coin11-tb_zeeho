import re
import time
import random
import uiautomator2 as u2

from utils import easy_ocr, get_current_app, get_connected_devices, select_device, QD_APP, start_app

PREFERRED_DEVICE = "192.168.70.154:39931"

TASK_SPECS = [
    {"name": "激励任务", "keywords": ["激励任务"]},
    {"name": "惊喜福利", "keywords": ["做任务领惊喜福利", "惊喜福利"]},
    {"name": "3个广告任务", "keywords": ["完成3个广告任务得奖励", "3个广告任务"]},
    {"name": "1个广告任务", "keywords": ["完成1个广告任务得奖励", "1个广告任务"]},
]

PENDING_ACTION_TEXTS = ["去完成", "去领取", "领奖励"]
DONE_ACTION_TEXTS = ["已完成", "已领取", "明日再来", "已达上限", "已结束"]


def normalize_text(text):
    text = (text or "").strip()
    return re.sub(r"\s+", "", text)


def ocr_items(d):
    result = []
    for item in easy_ocr(d.screenshot(), return_info=True):
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            continue
        bbox, text, conf = item
        txt = normalize_text(text)
        if not txt:
            continue
        try:
            x1 = float(bbox[0][0])
            y1 = float(bbox[0][1])
            x2 = float(bbox[2][0])
            y2 = float(bbox[2][1])
        except Exception:
            continue
        cx = int((x1 + x2) / 2)
        cy = int((y1 + y2) / 2)
        result.append(
            {
                "text": txt,
                "raw_text": str(text),
                "conf": float(conf),
                "bbox": bbox,
                "cx": cx,
                "cy": cy,
                "x1": int(min(x1, x2)),
                "y1": int(min(y1, y2)),
                "x2": int(max(x1, x2)),
                "y2": int(max(y1, y2)),
            }
        )
    return result


def click_center(d, item):
    d.click(item["cx"], item["cy"])


def is_reward_popup_text(full_text):
    return (
        any(k in full_text for k in ["恭喜", "奖励到账", "奖励已发放", "领取成功", "已获得"])
        and any(k in full_text for k in ["知道了", "我知道了", "确定", "收下"])
    )


def is_in_welfare_page(items, activity):
    full_text = " ".join(i["text"] for i in items)
    welfare_words = ["福利中心", "完成任务得奖励", "去完成", "激励任务", "惊喜福利", "广告任务"]
    return ("Browser" in (activity or "") or "QDBrowserActivity" in (activity or "")) and any(
        w in full_text for w in welfare_words
    )


def find_anchor_y(items):
    anchors = [i for i in items if "完成任务得奖励" in i["text"]]
    if not anchors:
        return None
    anchors.sort(key=lambda x: x["conf"], reverse=True)
    return anchors[0]["cy"]


def find_action_near_row(items, row_item, y_tolerance=120):
    candidates = []
    for i in items:
        if i["cx"] <= row_item["cx"] + 80:
            continue
        if abs(i["cy"] - row_item["cy"]) > y_tolerance:
            continue
        if any(t in i["text"] for t in PENDING_ACTION_TEXTS + DONE_ACTION_TEXTS):
            candidates.append(i)
    if not candidates:
        return None
    candidates.sort(key=lambda x: (abs(x["cy"] - row_item["cy"]), -x["cx"]))
    return candidates[0]


def find_task_row_and_action(items, spec, anchor_y=None):
    rows = []
    for i in items:
        if not any(k in i["text"] for k in spec["keywords"]):
            continue
        if anchor_y is not None and i["cy"] < anchor_y - 30:
            continue
        rows.append(i)
    if not rows:
        return None, None
    rows.sort(key=lambda x: x["cy"])
    row = rows[0]
    action = find_action_near_row(items, row)
    return row, action


def scroll_to_task_panel(d, max_rounds=8):
    for idx in range(max_rounds):
        items = ocr_items(d)
        has_anchor = find_anchor_y(items) is not None
        has_any_task = any(
            any(k in i["text"] for k in spec["keywords"]) for spec in TASK_SPECS for i in items
        )
        if has_anchor or has_any_task:
            return True
        if idx < max_rounds // 2:
            d.swipe_ext("up", scale=0.28)
        else:
            d.swipe_ext("down", scale=0.22)
        time.sleep(1.2)
    return False


def click_text_candidate(d, items, keywords, region="all", prefer_bottom=False):
    width, height = d.window_size()
    candidates = []
    for i in items:
        if not any(k in i["text"] for k in keywords):
            continue
        if region == "top-right":
            if not (i["cy"] < int(height * 0.34) and i["cx"] > int(width * 0.55)):
                continue
        elif region == "top-left":
            if not (i["cy"] < int(height * 0.34) and i["cx"] < int(width * 0.45)):
                continue
        candidates.append(i)
    if not candidates:
        return False
    if prefer_bottom:
        candidates.sort(key=lambda x: (-x["cy"], abs(x["cx"] - width // 2)))
    else:
        candidates.sort(key=lambda x: (x["cy"], -x["cx"]))
    click_center(d, candidates[0])
    return True


def close_reward_popup_if_any(d, items=None):
    if items is None:
        items = ocr_items(d)
    full_text = " ".join(i["text"] for i in items)
    if not is_reward_popup_text(full_text):
        return False
    if click_text_candidate(d, items, ["我知道了", "知道了", "确定", "收下"], region="all"):
        time.sleep(1)
        return True
    w, h = d.window_size()
    d.click(w // 2, int(h * 0.82))
    time.sleep(1)
    return True


def detect_countdown_seconds(text):
    patterns = [
        r"(\d+)秒后可领",
        r"再看(\d+)秒",
        r"剩余(\d+)秒",
        r"(\d+)s",
        r"(\d+)秒",
    ]
    best = None
    for p in patterns:
        for m in re.findall(p, text):
            try:
                n = int(m)
            except Exception:
                continue
            if 0 <= n <= 120:
                if best is None or n > best:
                    best = n
    return best


def do_brief_browse(d, seconds=18):
    start = time.time()
    while time.time() - start < seconds:
        try:
            d.swipe_ext("up", scale=0.28)
        except Exception:
            pass
        time.sleep(random.uniform(1.6, 2.8))


def page_state_signature(pkg, activity, items):
    top_lines = sorted(items, key=lambda x: x["cy"])[:12]
    text_key = "|".join(i["text"] for i in top_lines)
    return f"{pkg}|{activity}|{text_key[:220]}"


def is_pre_countdown_gate(full_text):
    gate_words = ["点击后", "可获得奖励", "点击去浏览", "放弃奖励", "现在退出就没有奖励", "进入详情页或第三方应用"]
    return any(w in full_text for w in gate_words)


def advance_pre_countdown_gate(d, items):
    cta_words = ["点击去浏览", "去浏览", "查看详情", "去看看", "了解详情", "继续看", "继续观看", "立即下载", "下载领取", "去使用"]
    non_click_hints = ["进入详情页或第三方应用", "广告", "点击后", "可获得奖励"]
    w, h = d.window_size()

    # 优先点底部 CTA，避免点到正文“点击后...可获得奖励”
    bottom_candidates = []
    for i in items:
        if not any(k in i["text"] for k in cta_words):
            continue
        if any(h in i["text"] for h in non_click_hints):
            continue
        if i["cy"] < int(h * 0.55):
            continue
        bottom_candidates.append(i)
    if bottom_candidates:
        bottom_candidates.sort(key=lambda x: (-x["cy"], abs(x["cx"] - w // 2)))
        click_center(d, bottom_candidates[0])
        print(f"[gate] 已点击底部引导按钮: {bottom_candidates[0]['raw_text']}")
        time.sleep(1.8)
        return True

    if click_text_candidate(d, items, cta_words, region="all"):
        print("[gate] 已点击引导按钮，等待页面变化")
        time.sleep(1.8)
        return True
    d.swipe_ext("up", scale=0.24)
    time.sleep(1.0)
    d.swipe_ext("down", scale=0.16)
    time.sleep(0.8)
    print("[gate] 文案按钮未命中，已执行滑动触发")
    return False


def try_close_ad_layer(d, items):
    close_selectors = [
        d(textMatches=r"跳过|关闭|退出|返回|关闭广告"),
        d(descriptionMatches=r".*(close|cancel|exit|skip|dismiss|关闭|跳过|返回|x|×|✕).*"),
        d(resourceIdMatches=r".*(close|cancel|exit|skip|dismiss|关闭|跳过|返回|x|×|✕).*"),
    ]
    for sel in close_selectors:
        try:
            if sel.exists:
                sel.click()
                return True
        except Exception:
            pass

    if click_text_candidate(d, items, ["跳过", "关闭", "返回", "×", "✕", "X"], region="top-right"):
        return True
    if click_text_candidate(d, items, ["跳过", "关闭", "返回", "×", "✕", "X"], region="top-left"):
        return True

    w, _ = d.window_size()
    for x, y in [(w - 40, 70), (w - 80, 110), (40, 70), (80, 110)]:
        d.click(x, y)
        time.sleep(0.2)
    return False


def recover_to_welfare_page(d, max_rounds=10):
    for idx in range(max_rounds):
        items = ocr_items(d)
        pkg, activity = get_current_app(d)
        activity = activity or ""
        full_text = " ".join(i["text"] for i in items)
        print(f"[recover {idx + 1}/{max_rounds}] app={pkg}/{activity}")
        close_reward_popup_if_any(d, items)
        if is_in_welfare_page(items, activity):
            print("[recover] 已回到福利任务页")
            return True
        if "ADActivity" in activity and "RewardvideoPortraitADActivity" not in activity:
            print("[recover] 命中 ADActivity，优先点击左上返回区")
            w, h = d.window_size()
            for pt in [(int(w * 0.06), int(h * 0.06)), (int(w * 0.10), int(h * 0.07)), (40, 90)]:
                d.click(pt[0], pt[1])
                time.sleep(0.5)
                ni = ocr_items(d)
                _, na = get_current_app(d)
                if is_in_welfare_page(ni, na):
                    print("[recover] ADActivity 左上返回成功")
                    return True
            print("[recover] 左上返回未生效，执行连续 back")
            d.press("back")
            time.sleep(0.8)
            d.press("back")
            time.sleep(1.0)
            continue
        if "RewardvideoPortraitADActivity" in activity:
            print("[recover] 命中 Rewardvideo 页面，执行角点关闭 + 双 back")
            w, h = d.window_size()
            if click_text_candidate(d, items, ["X", "×", "✕", "关闭", "跳过"], region="top-left"):
                time.sleep(0.5)
            if click_text_candidate(d, items, ["X", "×", "✕", "关闭", "跳过"], region="top-right"):
                time.sleep(0.5)
            hot_points = [
                (int(w * 0.06), int(h * 0.05)), (int(w * 0.10), int(h * 0.08)),
                (int(w * 0.94), int(h * 0.05)), (int(w * 0.90), int(h * 0.08)),
            ]
            for x, y in hot_points:
                d.click(x, y)
                time.sleep(0.25)
            if click_text_candidate(d, items, ["放弃奖励", "退出", "返回"], region="all", prefer_bottom=True):
                time.sleep(0.6)
            d.press("back")
            time.sleep(0.8)
            d.press("back")
            time.sleep(1.0)
            continue
        if "MainGroupActivity" in activity:
            print("[recover] 已退回主界面，尝试重新进入福利中心")
            # 先尝试进入“我”标签
            if not (d(text="我").click_exists(timeout=0.5) or d(text="我的").click_exists(timeout=0.5)):
                click_text_candidate(d, items, ["我", "我的"], region="all")
            time.sleep(1.2)
            # 再尝试点击“福利中心”
            for _ in range(3):
                nitems = ocr_items(d)
                if click_text_candidate(d, nitems, ["福利中心"], region="all"):
                    time.sleep(2.2)
                    break
                d.swipe_ext("up", scale=0.2)
                time.sleep(1.0)
            continue
        if pkg != QD_APP:
            print("[recover] 当前在外部应用，执行 back")
            d.press("back")
            time.sleep(1.5)
            continue
        if idx >= max_rounds - 3:
            print("[recover] 接近最大轮次，重启起点")
            start_app(d, QD_APP, init=True)
            time.sleep(2.0)
            continue
        if any(k in full_text for k in ["奖励", "广告", "详情", "点击后"]):
            print("[recover] 疑似广告层，优先尝试关闭控件")
        if try_close_ad_layer(d, items):
            time.sleep(1)
            continue
        if click_text_candidate(d, items, ["放弃奖励", "退出", "返回"], region="all", prefer_bottom=True):
            time.sleep(1.0)
            continue
        d.press("back")
        time.sleep(1.2)
    print("[recover] 未确认回到福利页")
    return False


def execute_after_click_task(d, timeout=210):
    print("已点击去完成，进入广告/浏览处理流程")
    start = time.time()
    external_watch_started = False
    last_sec = None
    same_sec_hits = 0
    last_sig = None
    sig_stable_hits = 0
    internal_landing_since = None
    landing_rounds = 0
    external_return_attempts = 0
    gate_post_stall_hits = 0

    while time.time() - start < timeout:
        pkg, activity = get_current_app(d)
        activity = activity or ""
        items = ocr_items(d)
        full_text = " ".join(i["text"] for i in items)
        sig = page_state_signature(pkg, activity, items)
        if sig == last_sig:
            sig_stable_hits += 1
        else:
            sig_stable_hits = 1
            last_sig = sig

        if close_reward_popup_if_any(d, items):
            pass

        if is_in_welfare_page(items, activity):
            if not any(k in full_text for k in ["恭喜", "奖励", "知道了"]):
                print("已回到福利任务页")
                return True

        if pkg != QD_APP:
            if not external_watch_started:
                print(f"检测到外部页面: {pkg}/{activity}，开始浏览后返回")
                external_watch_started = True
            external_return_attempts += 1
            do_brief_browse(d, seconds=20)
            d.press("back")
            time.sleep(1.8)
            landing_rounds += 1
            if external_return_attempts >= 3:
                print("外部页面回退多次未返回起点，主动拉起起点应用")
                start_app(d, QD_APP, init=False)
                time.sleep(2.0)
            continue
        else:
            external_return_attempts = 0

        # 起点内广告落地页（非 Rewardvideo 容器）需要先浏览一段时间再返回
        if "ADActivity" in activity and "RewardvideoPortraitADActivity" not in activity:
            if internal_landing_since is None:
                internal_landing_since = time.time()
                print(f"检测到起点内广告落地页: {activity}，先浏览再返回")
            elapsed = time.time() - internal_landing_since
            if elapsed < 18:
                do_brief_browse(d, seconds=4)
                continue
            print("落地页浏览时长已满足，执行 back 返回广告容器")
            d.press("back")
            time.sleep(1.5)
            internal_landing_since = None
            landing_rounds += 1
            continue
        else:
            internal_landing_since = None

        if is_pre_countdown_gate(full_text):
            if landing_rounds >= 1:
                # 已完成至少一次落地页浏览后，不再重复强制跳转，优先等计时/领奖励
                sec2 = detect_countdown_seconds(full_text)
                if sec2 is not None and sec2 > 0:
                    wait2 = min(max(sec2 // 2 + 1, 2), 8)
                    print(f"[gate-post] 已完成落地页浏览，等待计时 {sec2}s -> sleep {wait2}s")
                    time.sleep(wait2)
                    gate_post_stall_hits = 0
                    continue
                if click_text_candidate(d, items, ["领取", "去领取", "领奖励", "领取奖励"], region="all", prefer_bottom=True):
                    print("[gate-post] 已尝试点击领取按钮")
                    time.sleep(1.0)
                    gate_post_stall_hits = 0
                    continue
                if sig_stable_hits >= 4:
                    print("[gate-post] 页面无进展，执行受控 back")
                    d.press("back")
                    time.sleep(1.0)
                    gate_post_stall_hits += 1
                    if gate_post_stall_hits >= 6:
                        print("[gate-post] 连续无进展，触发收尾回退")
                        return recover_to_welfare_page(d, max_rounds=12)
                continue
            advanced = advance_pre_countdown_gate(d, items)
            if advanced:
                if sig_stable_hits >= 4:
                    print("[gate] 连续点击后页面仍未变化，改用 back+滑动切换层级")
                    d.press("back")
                    time.sleep(0.9)
                    d.swipe_ext("up", scale=0.22)
                    time.sleep(0.8)
                time.sleep(1.0)
                continue
            if sig_stable_hits >= 3:
                print("[gate] 页面长时间无变化，执行底部中点兜底点击")
                w, h = d.window_size()
                d.click(int(w * 0.5), int(h * 0.86))
                time.sleep(1.2)
            continue

        if any(k in full_text for k in ["了解详情", "了解更多", "继续看", "继续观看", "去看看"]):
            if landing_rounds >= 1:
                sec3 = detect_countdown_seconds(full_text)
                if sec3 is not None and sec3 > 0:
                    wait3 = min(max(sec3 // 2 + 1, 2), 8)
                    print(f"[cta-post] 落地页已完成，等待计时 {sec3}s -> sleep {wait3}s")
                    time.sleep(wait3)
                else:
                    time.sleep(1.2)
                continue
            if click_text_candidate(d, items, ["继续观看", "继续看", "了解详情", "了解更多", "去看看"], region="all"):
                print("已点击广告CTA，等待跳转/计时")
                time.sleep(2)
                continue

        if any(k in full_text for k in ["滑动", "上滑", "下滑", "拖动", "浏览"]):
            d.swipe_ext("up", scale=0.30)
            time.sleep(1.2)
            d.swipe_ext("down", scale=0.20)
            time.sleep(1.2)

        sec = detect_countdown_seconds(full_text)
        if sec is not None and sec > 0:
            if last_sec == sec:
                same_sec_hits += 1
            else:
                same_sec_hits = 1
                last_sec = sec

            if same_sec_hits >= 3:
                print(f"倒计时 {sec}s 连续出现 {same_sec_hits} 次，尝试推进页面变化")
                if click_text_candidate(d, items, ["继续观看", "继续看", "了解详情", "了解更多", "去看看"], region="all"):
                    time.sleep(1.8)
                else:
                    d.swipe_ext("up", scale=0.28)
                    time.sleep(1.0)
                if sec <= 5:
                    click_text_candidate(d, items, ["领取", "去领取", "领奖励", "领取奖励"], region="all")
                    time.sleep(0.8)
                if sig_stable_hits >= 5:
                    print("页面签名持续不变，补一次轻量 back")
                    d.press("back")
                    time.sleep(1.0)
            else:
                sleep_sec = min(max(sec // 2 + 1, 2), 8)
                print(f"检测到广告倒计时约 {sec}s，等待 {sleep_sec}s")
                time.sleep(sleep_sec)
            continue

        if try_close_ad_layer(d, items):
            time.sleep(1.2)
            continue

        d.press("back")
        time.sleep(1.2)

    print("任务流程超时，执行收尾回退")
    return recover_to_welfare_page(d, max_rounds=12)


def choose_device_for_qidianfuli(preferred_device=PREFERRED_DEVICE):
    devices = get_connected_devices()
    if not devices:
        raise RuntimeError("未检测到任何连接的安卓设备")
    if len(devices) == 1:
        print(f"仅检测到 1 台设备，自动选择: {devices[0]}")
        return devices[0]
    if preferred_device in devices:
        print(f"检测到多台设备，优先选择: {preferred_device}")
        return preferred_device
    print("检测到多台设备，但优先设备不在列表，切换为手动选择")
    return select_device()


def run_qidian_fuli_tasks(d):
    print("开始执行 qidian 福利中心广告任务（仅“完成任务得奖励”卡片）")

    # 预处理：如果当前残留在广告页/外部页，先回到福利中心
    items0 = ocr_items(d)
    _, activity0 = get_current_app(d)
    if not is_in_welfare_page(items0, activity0):
        print("当前不在福利任务页，先执行回退恢复")
        recover_to_welfare_page(d, max_rounds=15)

    if not scroll_to_task_panel(d, max_rounds=10):
        raise RuntimeError("未定位到“完成任务得奖励”区域，请确认当前在福利中心任务页")

    stats = {
        "already_done": 0,
        "executed_success": 0,
        "executed_failed": 0,
        "not_found": 0,
    }
    task_report = []

    for spec in TASK_SPECS:
        print(f"准备处理任务: {spec['name']}")
        handled = False
        task_status = "not_found"
        task_note = "未定位到任务行"

        for attempt in range(6):
            items = ocr_items(d)
            anchor_y = find_anchor_y(items)
            row, action = find_task_row_and_action(items, spec, anchor_y=anchor_y)

            if row is None:
                d.swipe_ext("up", scale=0.24)
                time.sleep(1.2)
                continue

            if action is None:
                task_status = "unknown_action"
                task_note = f"任务行已找到，但未识别到右侧动作按钮（第{attempt + 1}次）"
                d.swipe_ext("up", scale=0.18)
                time.sleep(1.0)
                continue

            action_text = action["text"]
            print(f"任务行命中: {row['raw_text']} | 动作: {action_text}")

            if any(k in action_text for k in DONE_ACTION_TEXTS):
                print("该任务已完成或暂不可执行，跳过")
                handled = True
                task_status = "already_done"
                task_note = f"按钮状态: {action['raw_text']}"
                stats["already_done"] += 1
                break

            if any(k in action_text for k in PENDING_ACTION_TEXTS):
                click_center(d, action)
                time.sleep(2.0)
                flow_ok = execute_after_click_task(d, timeout=210)
                back_ok = recover_to_welfare_page(d, max_rounds=10)
                handled = True
                if flow_ok or back_ok:
                    task_status = "executed_success"
                    task_note = f"已执行: {action['raw_text']}"
                    stats["executed_success"] += 1
                else:
                    task_status = "executed_failed"
                    task_note = f"执行后回退异常: {action['raw_text']}"
                    stats["executed_failed"] += 1
                break

            # 未知动作（既不是已完成也不是去完成），不执行点击，避免误触
            task_status = "unknown_action"
            task_note = f"检测到未知按钮文案，已跳过: {action['raw_text']}"
            d.swipe_ext("up", scale=0.18)
            time.sleep(1.0)

        if not handled:
            print(f"未成功执行任务: {spec['name']}（可能不在当前批次或已隐藏）")
            if task_status == "not_found":
                stats["not_found"] += 1
            elif task_status == "unknown_action":
                stats["not_found"] += 1

        task_report.append(
            {
                "task": spec["name"],
                "status": task_status,
                "note": task_note,
            }
        )

    print("qidian 福利任务流程结束")
    print("=== 最终完成统计 ===")
    for item in task_report:
        print(f"- {item['task']}: {item['status']} ({item['note']})")
    print(
        "总计: "
        f"已完成跳过={stats['already_done']}, "
        f"执行成功={stats['executed_success']}, "
        f"执行失败={stats['executed_failed']}, "
        f"未命中/未知按钮={stats['not_found']}"
    )


def main():
    device_id = choose_device_for_qidianfuli()
    d = u2.connect(device_id)
    run_qidian_fuli_tasks(d)


if __name__ == "__main__":
    main()
