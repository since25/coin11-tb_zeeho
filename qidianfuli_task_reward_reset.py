import time

import uiautomator2 as u2

from qidianfuli_task import (
    TASK_SPECS,
    DONE_ACTION_TEXTS,
    PENDING_ACTION_TEXTS,
    advance_pre_countdown_gate,
    bootstrap_to_welfare_center,
    choose_device_for_qidianfuli,
    click_center,
    click_rewardvideo_gate_cta,
    click_text_candidate,
    close_reward_popup_if_any,
    detect_countdown_seconds,
    do_brief_browse,
    find_anchor_y,
    find_task_row_and_action,
    is_pre_countdown_gate,
    is_welfare_task_page,
    ocr_items,
    page_items,
    page_state_signature,
    recover_to_welfare_page,
    try_close_ad_layer,
    welfare_task_rows,
)
from utils import QD_APP, get_current_app, start_app


def is_reward_success_text(full_text):
    return (
        any(k in full_text for k in ["恭喜", "奖励到账", "奖励已发放", "领取成功", "已获得"])
        and any(k in full_text for k in ["奖励", "章节卡", "点币", "积分", "礼包"])
    )


def restart_qidian_to_welfare(d, reason):
    print(f"[reward-reset] {reason}，重启起点并重进福利页")
    try:
        d.app_stop(QD_APP)
    except Exception:
        pass
    time.sleep(1.0)
    start_app(d, QD_APP, init=True)
    time.sleep(2.5)
    return bootstrap_to_welfare_center(d, max_rounds=6)


def execute_after_click_task_reward_reset(d, timeout=210):
    print("已点击去完成，进入广告/浏览处理流程（reward-reset 分支）")
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
    rewardvideo_gate_hits = 0
    rewardvideo_gate_failures = 0

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

        if is_reward_success_text(full_text):
            return restart_qidian_to_welfare(d, "检测到恭喜已获得奖励")

        if close_reward_popup_if_any(d, items):
            items = ocr_items(d)
            full_text = " ".join(i["text"] for i in items)
            if is_reward_success_text(full_text):
                return restart_qidian_to_welfare(d, "奖励弹窗关闭后仍识别到奖励成功")

        if is_welfare_task_page(d, page_items(d, prefer_hierarchy=True), activity):
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
        external_return_attempts = 0

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
        internal_landing_since = None

        if "RewardvideoPortraitADActivity" in activity:
            sec0 = detect_countdown_seconds(full_text)
            if sec0 is None and landing_rounds == 0:
                rewardvideo_gate_hits += 1
                print(f"[rewardvideo-gate] 未检测到倒计时，优先点击前置 CTA，第 {rewardvideo_gate_hits} 次")
                if click_rewardvideo_gate_cta(d):
                    time.sleep(2.0)
                    pkg2, act2 = get_current_app(d)
                    act2 = act2 or ""
                    items2 = ocr_items(d)
                    full_text2 = " ".join(i["text"] for i in items2)
                    sec1 = detect_countdown_seconds(full_text2)
                    if pkg2 != QD_APP or "RewardvideoPortraitADActivity" not in act2 or sec1 is not None:
                        rewardvideo_gate_hits = 0
                        rewardvideo_gate_failures = 0
                        continue
                    rewardvideo_gate_failures += 1
                    print(f"[rewardvideo-gate] CTA 点击后仍未进入倒计时，第 {rewardvideo_gate_failures}/3 次失败")
                    if rewardvideo_gate_failures >= 3:
                        return restart_qidian_to_welfare(d, "rewardvideo 前置页连续 3 次未进入倒计时")
                    continue
                if rewardvideo_gate_hits <= 5:
                    time.sleep(1.5)
                    continue
            else:
                rewardvideo_gate_hits = 0
                rewardvideo_gate_failures = 0

        if is_pre_countdown_gate(full_text):
            if landing_rounds >= 1:
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

        if "RewardvideoPortraitADActivity" in activity and rewardvideo_gate_hits > 0:
            print("[rewardvideo-gate] 仍在前置页，暂不执行 back")
            time.sleep(1.2)
            continue

        d.press("back")
        time.sleep(1.2)

    print("任务流程超时，执行收尾回退")
    return recover_to_welfare_page(d, max_rounds=12)


def run_qidian_fuli_tasks_reward_reset(d):
    print("开始执行 qidian 福利中心广告任务（reward-reset 分支）")

    if not bootstrap_to_welfare_center(d, max_rounds=8):
        raise RuntimeError("初始化失败：未能自动进入起点福利中心")

    stats = {
        "already_done": 0,
        "executed_success": 0,
        "executed_failed": 0,
        "not_found": 0,
    }

    for spec in TASK_SPECS:
        print(f"准备处理任务: {spec['name']}")
        handled = False
        max_clicks = int(spec.get("max_clicks", 1))
        executed_times = 0

        for run_idx in range(max_clicks):
            if not bootstrap_to_welfare_center(d, max_rounds=4):
                print(f"{spec['name']} 第 {run_idx + 1} 轮前无法恢复到福利页")
                stats["executed_failed"] += 1
                handled = True
                break

            print(f"{spec['name']} 第 {run_idx + 1}/{max_clicks} 轮检查")
            rows = welfare_task_rows(d)
            row = next((r for r in rows if any(k in r["full_text"] for k in spec["keywords"])), None)
            action = row["action"] if row else None
            if row is None:
                items = page_items(d, prefer_hierarchy=True)
                anchor_y = find_anchor_y(items)
                row, action = find_task_row_and_action(items, spec, anchor_y=anchor_y)

            if row is None or action is None:
                print(f"未成功执行任务: {spec['name']}（可能不在当前批次或已隐藏）")
                continue

            action_text = action["text"]
            row_text = row.get("raw_text") or row.get("full_text") or row.get("text") or ""
            print(f"任务行命中: {row_text} | 动作: {action_text}")

            if any(k in action_text for k in DONE_ACTION_TEXTS):
                print("该任务已完成或暂不可执行，跳过")
                stats["already_done"] += 1
                handled = True
                break

            if any(k in action_text for k in PENDING_ACTION_TEXTS):
                click_center(d, action)
                time.sleep(2.0)
                flow_ok = execute_after_click_task_reward_reset(d, timeout=210)
                back_ok = bootstrap_to_welfare_center(d, max_rounds=4) if not flow_ok else True
                executed_times += 1
                handled = True
                if flow_ok or back_ok:
                    stats["executed_success"] += 1
                else:
                    stats["executed_failed"] += 1
                if max_clicks == 1:
                    break
                continue

            print(f"未知动作，跳过: {action_text}")
            handled = True
            stats["not_found"] += 1
            break

        if not handled:
            stats["not_found"] += 1

    print("qidian 福利任务 reward-reset 分支结束")
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
    run_qidian_fuli_tasks_reward_reset(d)


if __name__ == "__main__":
    main()
