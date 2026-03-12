import re
import time
import random
import xml.etree.ElementTree as ET
import uiautomator2 as u2

from utils import easy_ocr, get_current_app, get_connected_devices, select_device, QD_APP, start_app

PREFERRED_DEVICE = "192.168.70.154:39931"

TASK_SPECS = [
    {"name": "激励任务", "keywords": ["激励任务"], "max_clicks": 10},
    {"name": "惊喜福利", "keywords": ["做任务领惊喜福利", "惊喜福利"]},
    {"name": "3个广告任务", "keywords": ["完成3个广告任务得奖励", "3个广告任务"], "max_clicks": 3},
    {"name": "1个广告任务", "keywords": ["完成1个广告任务得奖励", "1个广告任务"]},
]

PENDING_ACTION_TEXTS = ["去完成", "去领取", "领奖励"]
DONE_ACTION_TEXTS = ["已完成", "已领取", "明日再来", "已达上限", "已结束"]
WELFARE_HINT_WORDS = ["福利中心", "完成任务得奖励", "去完成", "去领取", "激励任务", "惊喜福利", "广告任务", "领奖励"]
WELFARE_ACTIVITY_HINTS = ("Browser", "QDBrowserActivity")
AD_LAYER_HINT_WORDS = ["点击后", "进入详情页", "第三方应用", "放弃奖励", "现在退出就没有奖励", "继续观看", "查看详情"]


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


def parse_bounds(bounds):
    nums = re.findall(r"\d+", bounds or "")
    if len(nums) != 4:
        return None
    x1, y1, x2, y2 = map(int, nums)
    return x1, y1, x2, y2


def extract_cooldown_action(full_text, row_bounds=None):
    full_text = normalize_text(full_text)
    m = re.search(r"(剩余?|余)(\d{1,2}:\d{2}(?::\d{2})?)", full_text)
    if not m:
        m = re.search(r"(剩)(\d{1,2}:\d{2}(?::\d{2})?)", full_text)
    if not m:
        return None
    text = f"剩{m.group(2)}"
    action = {
        "text": text,
        "raw_text": text,
    }
    if row_bounds:
        x1, y1, x2, y2 = row_bounds
        action.update(
            {
                "cx": int(x1 + (x2 - x1) * 0.86),
                "cy": int((y1 + y2) / 2),
                "x1": int(x1 + (x2 - x1) * 0.72),
                "y1": y1,
                "x2": x2,
                "y2": y2,
            }
        )
    return action


def hierarchy_items(d):
    items = []
    try:
        root = ET.fromstring(d.dump_hierarchy())
    except Exception:
        return items
    for node in root.iter("node"):
        text = (node.get("text") or node.get("content-desc") or "").strip()
        bounds = parse_bounds(node.get("bounds") or "")
        if not text or not bounds:
            continue
        x1, y1, x2, y2 = bounds
        items.append(
            {
                "text": normalize_text(text),
                "raw_text": text,
                "conf": 1.0,
                "bbox": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
                "cx": int((x1 + x2) / 2),
                "cy": int((y1 + y2) / 2),
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "resource_id": node.get("resource-id") or "",
                "class_name": node.get("class") or "",
                "clickable": (node.get("clickable") == "true"),
            }
        )
    items.sort(key=lambda x: (x["cy"], x["x1"]))
    return items


def page_items(d, prefer_hierarchy=False):
    pkg, activity = get_current_app(d)
    activity = activity or ""
    use_hierarchy = prefer_hierarchy or pkg == QD_APP or "Browser" in activity or "MainGroupActivity" in activity
    if use_hierarchy:
        items = hierarchy_items(d)
        if items:
            return items
    return ocr_items(d)


def welfare_task_rows(d):
    rows = []
    try:
        root = ET.fromstring(d.dump_hierarchy())
    except Exception:
        return rows

    for node in root.iter("node"):
        rid = node.get("resource-id") or ""
        if not rid.startswith("task_row_"):
            continue
        bounds = parse_bounds(node.get("bounds") or "")
        if not bounds:
            continue
        texts = []
        action = None
        for child in node.iter("node"):
            text = normalize_text(child.get("text") or "")
            if text:
                texts.append(text)
            if text in PENDING_ACTION_TEXTS + DONE_ACTION_TEXTS:
                cb = parse_bounds(child.get("bounds") or "")
                if not cb:
                    continue
                cx = int((cb[0] + cb[2]) / 2)
                cy = int((cb[1] + cb[3]) / 2)
                action = {
                    "text": text,
                    "raw_text": child.get("text") or text,
                    "cx": cx,
                    "cy": cy,
                    "x1": cb[0],
                    "y1": cb[1],
                    "x2": cb[2],
                    "y2": cb[3],
                }
        rows.append(
            {
                "resource_id": rid,
                "texts": texts,
                "full_text": "".join(texts),
                "cy": int((bounds[1] + bounds[3]) / 2),
                "x1": bounds[0],
                "y1": bounds[1],
                "x2": bounds[2],
                "y2": bounds[3],
                "action": action or extract_cooldown_action("".join(texts), row_bounds=bounds),
            }
        )
    rows.sort(key=lambda x: x["cy"])
    return rows


def is_welfare_task_page(d, items=None, activity=None):
    if items is None:
        items = page_items(d, prefer_hierarchy=True)
    full_text = compact_page_text(items)
    rows = welfare_task_rows(d)
    if rows:
        return True
    if activity is None:
        _, activity = get_current_app(d)
    activity = activity or ""
    has_anchor = "完成任务得奖励" in full_text
    has_action = "去完成" in full_text or "去领取" in full_text or "领奖励" in full_text
    return ("QDBrowserActivity" in activity or "Browser" in activity) and has_anchor and has_action


def click_me_tab(d):
    me_candidates = [
        d(resourceIdMatches=r".*tab_me.*|.*f6.*", text="我的"),
        d(resourceId="com.qidian.QDReader:id/view_tab_title_title", text="我"),
        d(text="我"),
        d(text="我的"),
    ]
    for sel in me_candidates:
        try:
            if sel.exists:
                sel.click()
                return True
        except Exception:
            pass

    try:
        root = ET.fromstring(d.dump_hierarchy())
        for node in root.iter("node"):
            if (node.get("text") or "").strip() != "我":
                continue
            bounds = parse_bounds(node.get("bounds") or "")
            if not bounds:
                continue
            x1, y1, x2, y2 = bounds
            d.click(int((x1 + x2) / 2), int((y1 + y2) / 2))
            return True
    except Exception:
        pass

    # 三星设备底部 tab 的稳定中心区域，避免点到导航栏边缘
    w, h = d.window_size()
    d.click(int(w * 0.875), int(h * 0.952))
    return True


def force_back_to_maingroup(d, max_steps=8):
    for step in range(max_steps):
        pkg, activity = get_current_app(d)
        activity = activity or ""
        if pkg != QD_APP:
            d.press("back")
            time.sleep(1.0)
            continue
        if "MainGroupActivity" in activity:
            return True
        if "QDBrowserActivity" in activity:
            return True
        d.press("back")
        time.sleep(1.0)
    pkg, activity = get_current_app(d)
    activity = activity or ""
    return pkg == QD_APP and ("MainGroupActivity" in activity or "QDBrowserActivity" in activity)


def group_items_by_line(items, y_tolerance=42):
    lines = []
    for item in sorted(items, key=lambda x: (x["cy"], x["x1"])):
        target = None
        best_delta = None
        for line in lines:
            delta = abs(item["cy"] - line["cy"])
            if delta > y_tolerance:
                continue
            if best_delta is None or delta < best_delta:
                best_delta = delta
                target = line
        if target is None:
            lines.append({"cy": item["cy"], "items": [item]})
            continue
        target["items"].append(item)
        target["cy"] = int(sum(i["cy"] for i in target["items"]) / len(target["items"]))
    for line in lines:
        line["items"].sort(key=lambda x: x["x1"])
        line["text"] = "".join(i["text"] for i in line["items"])
    lines.sort(key=lambda x: x["cy"])
    return lines


def compact_page_text(items):
    return "".join(i["text"] for i in sorted(items, key=lambda x: (x["cy"], x["x1"])))


def build_virtual_item(text, source_items):
    xs1 = [i["x1"] for i in source_items]
    ys1 = [i["y1"] for i in source_items]
    xs2 = [i["x2"] for i in source_items]
    ys2 = [i["y2"] for i in source_items]
    return {
        "text": text,
        "raw_text": text,
        "conf": min((float(i["conf"]) for i in source_items), default=0.0),
        "bbox": [[min(xs1), min(ys1)], [max(xs2), min(ys1)], [max(xs2), max(ys2)], [min(xs1), max(ys2)]],
        "cx": int((min(xs1) + max(xs2)) / 2),
        "cy": int((min(ys1) + max(ys2)) / 2),
        "x1": min(xs1),
        "y1": min(ys1),
        "x2": max(xs2),
        "y2": max(ys2),
    }


def click_center(d, item):
    d.click(item["cx"], item["cy"])


def is_reward_popup_text(full_text):
    return (
        any(k in full_text for k in ["恭喜", "奖励到账", "奖励已发放", "领取成功", "已获得"])
        and any(k in full_text for k in ["知道了", "我知道了", "确定", "收下"])
    )


def is_in_welfare_page(items, activity):
    full_text = compact_page_text(items)
    activity = activity or ""
    keyword_hits = sum(1 for w in WELFARE_HINT_WORDS if w in full_text)
    has_task_layout = ("去完成" in full_text or "去领取" in full_text) and any(
        w in full_text for w in ["激励任务", "惊喜福利", "广告任务", "奖励"]
    )
    return (
        any(hint in activity for hint in WELFARE_ACTIVITY_HINTS) and (keyword_hits >= 1 or has_task_layout)
    ) or (keyword_hits >= 2) or has_task_layout


def find_anchor_y(items):
    anchors = [
        i for i in items
        if "完成任务得奖励" in i["text"] or ("任务" in i["text"] and "奖励" in i["text"])
    ]
    if not anchors:
        for line in group_items_by_line(items):
            if "完成任务得奖励" in line["text"] or ("任务" in line["text"] and "奖励" in line["text"]):
                anchors.append(build_virtual_item(line["text"], line["items"]))
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
        line_items = [
            i for i in items
            if i["cx"] > row_item["cx"] and abs(i["cy"] - row_item["cy"]) <= y_tolerance
        ]
        if line_items:
            merged = "".join(i["text"] for i in sorted(line_items, key=lambda x: x["x1"]))
            for text in PENDING_ACTION_TEXTS + DONE_ACTION_TEXTS:
                if text in merged:
                    return build_virtual_item(text, line_items)
        return None
    candidates.sort(key=lambda x: (abs(x["cy"] - row_item["cy"]), -x["cx"]))
    return candidates[0]


def find_task_row_and_action(items, spec, anchor_y=None):
    rows = []
    for i in items:
        if any(k in i["text"] for k in spec["keywords"]):
            if anchor_y is not None and i["cy"] < anchor_y - 30:
                continue
            rows.append(i)
    if not rows:
        for line in group_items_by_line(items):
            if not any(k in line["text"] for k in spec["keywords"]):
                continue
            if anchor_y is not None and line["cy"] < anchor_y - 30:
                continue
            rows.append(build_virtual_item(line["text"], line["items"]))
    if not rows:
        return None, None
    rows.sort(key=lambda x: x["cy"])
    row = rows[0]
    action = find_action_near_row(items, row)
    if action is None:
        row_text = row.get("raw_text") or row.get("full_text") or row.get("text") or ""
        row_bounds = None
        if all(k in row for k in ("x1", "y1", "x2", "y2")):
            row_bounds = (row["x1"], row["y1"], row["x2"], row["y2"])
        action = extract_cooldown_action(row_text, row_bounds=row_bounds)
    return row, action


def enter_welfare_center_selector_first(d, max_rounds=6):
    """
    从起点主界面进入福利中心：selector/xpath 优先，OCR 仅兜底。
    该函数对 OCR 质量依赖更低，适合 Linux + pytesseract 场景。
    """
    # 1) 先确保进入“我/我的”页
    clicked_me = click_me_tab(d)
    if not clicked_me:
        items = page_items(d, prefer_hierarchy=True)
        if click_text_candidate(d, items, ["我的", "我"], region="all"):
            clicked_me = True
    if not clicked_me:
        click_me_tab(d)
    time.sleep(1.8)

    # 2) 在“我”页找“福利中心”
    for i in range(max_rounds):
        benefit_parent = d.xpath('//*[@text="福利中心"]/..')
        benefit_grand = d.xpath('//*[@text="福利中心"]/../..')
        benefit_btn = d(text="福利中心")

        if benefit_parent.exists:
            benefit_parent.click()
            time.sleep(2.5)
            return True
        if benefit_grand.exists:
            benefit_grand.click()
            time.sleep(2.5)
            return True
        if benefit_btn.exists:
            benefit_btn.click()
            time.sleep(2.5)
            return True

        # OCR 兜底
        items = page_items(d, prefer_hierarchy=True)
        if click_text_candidate(d, items, ["福利中心"], region="all"):
            time.sleep(2.5)
            return True

        d.swipe_ext("up", scale=0.20)
        time.sleep(1.0)
        print(f"查找福利中心中... {i + 1}/{max_rounds}")

    return False


def scroll_to_task_panel(d, max_rounds=8):
    for idx in range(max_rounds):
        rows = welfare_task_rows(d)
        if rows:
            return True
        items = page_items(d, prefer_hierarchy=True)
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
        for line in group_items_by_line(items):
            if not any(k in line["text"] for k in keywords):
                continue
            virtual = build_virtual_item(line["text"], line["items"])
            if region == "top-right":
                if not (virtual["cy"] < int(height * 0.34) and virtual["cx"] > int(width * 0.55)):
                    continue
            elif region == "top-left":
                if not (virtual["cy"] < int(height * 0.34) and virtual["cx"] < int(width * 0.45)):
                    continue
            candidates.append(virtual)
    if not candidates:
        return False
    if prefer_bottom:
        candidates.sort(key=lambda x: (-x["cy"], abs(x["cx"] - width // 2)))
    else:
        candidates.sort(key=lambda x: (x["cy"], -x["cx"]))
    click_center(d, candidates[0])
    return True


def close_reward_popup_if_any(d, items=None):
    hier_items = hierarchy_items(d)
    full_text_hier = " ".join(i["text"] for i in hier_items)
    if items is None:
        items = hier_items or ocr_items(d)
    full_text = " ".join(i["text"] for i in items)
    if not is_reward_popup_text(full_text):
        if not is_reward_popup_text(full_text_hier):
            return False
        full_text = full_text_hier
        if hier_items:
            items = hier_items

    ack_selectors = [
        d(text="我知道了"),
        d(text="知道了"),
        d(text="确定"),
        d(text="收下"),
        d(textMatches=r"^(我知道了|知道了|确定|收下)$"),
    ]
    for sel in ack_selectors:
        try:
            if sel.exists:
                sel.click()
                time.sleep(1)
                return True
        except Exception:
            pass

    if click_text_candidate(d, items, ["我知道了", "知道了", "确定", "收下"], region="all", prefer_bottom=True):
        time.sleep(1)
        return True
    w, h = d.window_size()
    d.click(w // 2, int(h * 0.82))
    time.sleep(1)
    return True


def close_system_permission_dialog_if_any(d, items=None):
    pkg, activity = get_current_app(d)
    activity = activity or ""
    if items is None:
        items = page_items(d, prefer_hierarchy=True)
    full_text = compact_page_text(items)

    permission_hints = [
        "权限", "允许", "位置信息", "麦克风", "相机", "通讯录", "通知",
        "照片", "存储", "录音", "附近设备", "此设备的位置", "仅在使用该应用时",
    ]
    is_permission_page = (
        "GrantPermissionsActivity" in activity
        or "permissioncontroller" in pkg
        or any(h in full_text for h in permission_hints)
    )
    if not is_permission_page:
        return False

    selectors = [
        d(text="不允许"),
        d(text="拒绝"),
        d(text="仅限这一次"),
        d(text="稍后再说"),
        d(text="取消"),
        d(textMatches=r"^(不允许|拒绝|仅限这一次|稍后再说|取消)$"),
    ]
    for sel in selectors:
        try:
            if sel.exists:
                sel.click()
                print("[permission] 已处理系统权限弹窗")
                time.sleep(1.0)
                return True
        except Exception:
            pass

    if click_text_candidate(d, items, ["不允许", "拒绝", "仅限这一次", "稍后再说", "取消"], region="all", prefer_bottom=True):
        print("[permission] 已处理系统权限弹窗")
        time.sleep(1.0)
        return True
    return False


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


def is_rewardvideo_stuck_reward_page(full_text, items=None):
    if "恭喜已获得奖励" not in full_text:
        return False
    if "立即下载" not in full_text:
        return False
    if "进入详情页或第三方应用" not in full_text:
        return False
    if items is not None and len(items) <= 3:
        return True
    return True


def is_rewardvideo_recommend_popup(full_text):
    popup_words = ["专属推荐", "去微信看看", "查看详情", "立即查看", "立即打开", "去看看", "了解更多"]
    reward_gate_words = ["点击后", "看15秒可获得奖励", "进入详情页或第三方应用", "了解更多"]
    return "专属推荐" in full_text or (
        any(w in full_text for w in popup_words)
        and not any(w in full_text for w in ["恭喜已获得奖励", "立即下载", "进入详情页或第三方应用"])
    ) or (
        any(w in full_text for w in reward_gate_words)
        and "立即下载" not in full_text
    )


def try_close_rewardvideo_recommend_popup(d, items=None, source="gate"):
    if items is None:
        items = ocr_items(d)
    full_text = compact_page_text(items)
    if not is_rewardvideo_recommend_popup(full_text):
        return False

    if click_text_candidate(d, items, ["X", "×", "✕", "关闭"], region="top-left"):
        time.sleep(0.8)
        print(f"[{source}] 已点击前置卡左上关闭")
        return True
    if click_text_candidate(d, items, ["X", "×", "✕", "关闭"], region="top-right"):
        time.sleep(0.8)
        print(f"[{source}] 已点击前置卡右上关闭")
        return True

    w, h = d.window_size()
    hot_points = [
        (int(w * 0.94), int(h * 0.06)),
        (int(w * 0.90), int(h * 0.08)),
        (int(w * 0.88), int(h * 0.10)),
        (int(w * 0.06), int(h * 0.06)),
        (int(w * 0.08), int(h * 0.08)),
        (int(w * 0.10), int(h * 0.10)),
    ]
    for x, y in hot_points:
        d.click(x, y)
        time.sleep(0.5)
        pkg, activity = get_current_app(d)
        if pkg != QD_APP or "RewardvideoPortraitADActivity" not in (activity or ""):
            print(f"[{source}] 前置卡角点热区关闭成功: ({x},{y})")
            return True
        items2 = ocr_items(d)
        full_text2 = compact_page_text(items2)
        if not is_rewardvideo_recommend_popup(full_text2):
            print(f"[{source}] 前置卡角点热区已关闭弹卡: ({x},{y})")
            return True
    return False


def click_rewardvideo_gate_cta(d):
    """
    腾讯激励视频前置页经常把 CTA 画成无文本自定义控件。
    这里优先点击实测稳定的底部 CTA 区域。
    """
    w, h = d.window_size()
    hot_points = [
        (w // 2, int(h * 0.805)),
        (w // 2, int(h * 0.835)),
        (int(w * 0.72), int(h * 0.805)),
    ]
    for x, y in hot_points:
        d.click(x, y)
        print(f"[gate] 已点击前置页 CTA 热区: ({x},{y})")
        time.sleep(1.5)
        pkg, act = get_current_app(d)
        act = act or ""
        if pkg != QD_APP or "RewardvideoPortraitADActivity" not in act:
            return True
    return False


def advance_pre_countdown_gate(d, items):
    cta_words = ["点击去浏览", "去浏览", "查看详情", "去看看", "了解详情", "继续看", "继续观看", "立即下载", "下载领取", "去使用"]
    non_click_hints = ["进入详情页或第三方应用", "广告", "点击后", "可获得奖励"]
    w, h = d.window_size()

    if click_rewardvideo_gate_cta(d):
        return True

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


def is_rewardvideo_page(pkg, activity):
    return pkg == QD_APP and "RewardvideoPortraitADActivity" in (activity or "")


def click_rewardvideo_exit_confirm(d, items=None):
    if items is None:
        items = ocr_items(d)
    full_text = compact_page_text(items)
    confirm_words = [
        "放弃奖励", "确认退出", "仍要退出", "退出广告", "狠心离开",
        "残忍离开", "退出并返回", "确认离开",
    ]
    exit_hints = [
        "现在退出就没有奖励", "退出后将失去奖励", "放弃奖励", "确认退出",
        "仍要退出", "退出广告", "离开将无法获得奖励",
    ]
    if not any(word in full_text for word in exit_hints + confirm_words):
        return False

    selectors = [
        d(textMatches=r".*(放弃奖励|确认退出|仍要退出|退出广告|狠心离开|残忍离开|退出并返回|确认离开).*"),
        d(descriptionMatches=r".*(放弃奖励|确认退出|仍要退出|退出广告|狠心离开|残忍离开|退出并返回|确认离开).*"),
    ]
    for sel in selectors:
        try:
            if sel.exists:
                sel.click()
                time.sleep(0.9)
                return True
        except Exception:
            pass

    if click_text_candidate(d, items, confirm_words, region="all", prefer_bottom=True):
        time.sleep(0.9)
        return True
    return False


def click_rewardvideo_continue_browse(d, items=None, source="gate"):
    if items is None:
        items = ocr_items(d)
    full_text = compact_page_text(items)
    continue_words = ["点击去浏览", "去浏览", "继续浏览", "继续观看", "继续看", "去查看", "查看详情"]
    exit_hints = ["现在退出就没有奖励", "即可领取奖励", "点击广告浏览", "可获得奖励", "放弃奖励"]
    if not any(word in full_text for word in exit_hints):
        return False

    if click_text_candidate(d, items, continue_words, region="all", prefer_bottom=True):
        print(f"[{source}] 已点击继续浏览按钮")
        time.sleep(1.0)
        return True
    return False


def try_exit_rewardvideo_page(d, items=None, source="recover"):
    pkg, activity = get_current_app(d)
    activity = activity or ""
    if not is_rewardvideo_page(pkg, activity):
        return False
    if items is None:
        items = page_items(d, prefer_hierarchy=True)
    full_text = compact_page_text(items)

    # 这类“恭喜已获得奖励 + 立即下载”页面在真机上会拦截 back 和右上角点击。
    # 奖励已经到账，直接重启起点比反复卡在 Rewardvideo 更稳。
    if is_rewardvideo_stuck_reward_page(full_text, items):
        print(f"[{source}] 命中 Rewardvideo 奖励卡死页，直接重启起点恢复")
        start_app(d, QD_APP, init=True)
        time.sleep(2.5)
        return True

    # 有些广告先弹退出确认框，优先点确认按钮，避免 back 只是在框内兜圈。
    if click_rewardvideo_exit_confirm(d, items):
        pkg, activity = get_current_app(d)
        if not is_rewardvideo_page(pkg, activity):
            print(f"[{source}] Rewardvideo 退出确认已生效")
            return True
        items = page_items(d, prefer_hierarchy=True)

    if try_close_ad_layer(d, items):
        pkg, activity = get_current_app(d)
        if not is_rewardvideo_page(pkg, activity):
            print(f"[{source}] Rewardvideo 角点关闭已生效")
            return True
        items = page_items(d, prefer_hierarchy=True)

    w, h = d.window_size()
    hot_points = [
        (int(w * 0.06), int(h * 0.05)),
        (int(w * 0.10), int(h * 0.08)),
        (int(w * 0.12), int(h * 0.11)),
        (int(w * 0.94), int(h * 0.05)),
        (int(w * 0.90), int(h * 0.08)),
        (int(w * 0.88), int(h * 0.11)),
    ]
    for x, y in hot_points:
        d.click(x, y)
        time.sleep(0.35)
        pkg, activity = get_current_app(d)
        if not is_rewardvideo_page(pkg, activity):
            print(f"[{source}] Rewardvideo 角点热区命中: ({x},{y})")
            return True

    for step in range(2):
        d.press("back")
        time.sleep(0.9 if step == 0 else 1.1)
        pkg, activity = get_current_app(d)
        if not is_rewardvideo_page(pkg, activity):
            print(f"[{source}] Rewardvideo back 已退出，第 {step + 1} 次")
            return True
        items = page_items(d, prefer_hierarchy=True)
        if click_rewardvideo_exit_confirm(d, items):
            pkg, activity = get_current_app(d)
            if not is_rewardvideo_page(pkg, activity):
                print(f"[{source}] Rewardvideo back 后确认退出成功")
                return True
            items = page_items(d, prefer_hierarchy=True)

    return False


def recover_to_welfare_page(d, max_rounds=10):
    rewardvideo_streak = 0
    for idx in range(max_rounds):
        items = page_items(d, prefer_hierarchy=True)
        pkg, activity = get_current_app(d)
        activity = activity or ""
        full_text = " ".join(i["text"] for i in items)
        print(f"[recover {idx + 1}/{max_rounds}] app={pkg}/{activity}")
        if close_system_permission_dialog_if_any(d, items):
            continue
        close_reward_popup_if_any(d, items)
        if is_in_welfare_page(items, activity):
            print("[recover] 已回到福利任务页")
            return True
        if "ADActivity" in activity and "RewardvideoPortraitADActivity" not in activity:
            rewardvideo_streak = 0
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
            rewardvideo_streak += 1
            print("[recover] 命中 Rewardvideo 页面，尝试受控退出")
            if try_exit_rewardvideo_page(d, items=items, source="recover"):
                rewardvideo_streak = 0
                continue
            if rewardvideo_streak >= 5:
                print("[recover] Rewardvideo 连续卡住，强制重启起点")
                start_app(d, QD_APP, init=True)
                time.sleep(2.2)
                rewardvideo_streak = 0
            continue
        rewardvideo_streak = 0
        if "MainGroupActivity" in activity:
            print("[recover] 已退回主界面，尝试重新进入福利中心")
            enter_welfare_center_selector_first(d, max_rounds=4)
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
        if any(k in full_text for k in AD_LAYER_HINT_WORDS):
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
    rewardvideo_gate_hits = 0
    pre_gate_stall_hits = 0
    pre_gate_close_fail_hits = 0
    jump_confirmed = False

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
            items = page_items(d, prefer_hierarchy=True)
            pkg, activity = get_current_app(d)
            activity = activity or ""
            full_text = " ".join(i["text"] for i in items)
            sig = page_state_signature(pkg, activity, items)
            last_sig = sig
            sig_stable_hits = 1

        perm_items = page_items(d, prefer_hierarchy=True)
        if close_system_permission_dialog_if_any(d, perm_items):
            last_sig = None
            sig_stable_hits = 0
            continue

        if is_in_welfare_page(items, activity):
            if not is_reward_popup_text(full_text):
                print("已回到福利任务页")
                return True

        if pkg != QD_APP:
            jump_confirmed = True
            pre_gate_stall_hits = 0
            pre_gate_close_fail_hits = 0
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
            jump_confirmed = True
            pre_gate_stall_hits = 0
            pre_gate_close_fail_hits = 0
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

        # 激励视频页常先出现“现在退出就没有奖励哦/点击去浏览”前置层。
        # 这时不能过早 back，优先点底部固定 CTA 触发正式计时。
        if "RewardvideoPortraitADActivity" in activity:
            sec0 = detect_countdown_seconds(full_text)
            if jump_confirmed or landing_rounds >= 1:
                if sec0 is not None and sec0 > 0:
                    sleep_sec = min(max(sec0 // 2 + 1, 2), 8)
                    print(f"[rewardvideo-post] 已触发跳转，按倒计时等待 {sec0}s -> sleep {sleep_sec}s")
                    time.sleep(sleep_sec)
                    continue
                if sig_stable_hits >= 3:
                    print("[rewardvideo-post] 已触发跳转，后续内容不再解析，直接收尾返回")
                    return recover_to_welfare_page(d, max_rounds=8)
                time.sleep(1.2)
                continue
            if is_rewardvideo_stuck_reward_page(full_text):
                print("[rewardvideo] 命中奖励卡死页，直接重启起点恢复")
                start_app(d, QD_APP, init=True)
                time.sleep(2.5)
                return recover_to_welfare_page(d, max_rounds=6)
            if click_rewardvideo_continue_browse(d, items=items, source="rewardvideo-gate"):
                rewardvideo_gate_hits = 0
                pre_gate_stall_hits = 0
                pre_gate_close_fail_hits = 0
                continue
            if is_rewardvideo_recommend_popup(full_text):
                pre_gate_stall_hits = pre_gate_stall_hits + 1 if sig_stable_hits >= 2 else pre_gate_stall_hits
                if try_close_rewardvideo_recommend_popup(d, items=items, source="rewardvideo-gate"):
                    items = ocr_items(d)
                    full_text = compact_page_text(items)
                    if click_rewardvideo_continue_browse(d, items=items, source="rewardvideo-gate"):
                        rewardvideo_gate_hits = 0
                        pre_gate_stall_hits = 0
                        pre_gate_close_fail_hits = 0
                        continue
                    rewardvideo_gate_hits = 0
                    pre_gate_stall_hits = 0
                    pre_gate_close_fail_hits = 0
                    time.sleep(1.2)
                    continue
                pre_gate_close_fail_hits += 1
                if pre_gate_close_fail_hits >= 3 or pre_gate_stall_hits >= 5:
                    print("[rewardvideo-gate] 前置领奖卡连续无进展，执行收尾恢复")
                    return recover_to_welfare_page(d, max_rounds=8)
            if sec0 is None and landing_rounds == 0:
                rewardvideo_gate_hits += 1
                print(f"[rewardvideo-gate] 未检测到倒计时，优先点击前置 CTA，第 {rewardvideo_gate_hits} 次")
                if click_rewardvideo_gate_cta(d):
                    pre_gate_stall_hits = 0
                    pre_gate_close_fail_hits = 0
                    time.sleep(2.0)
                    continue
                if rewardvideo_gate_hits <= 3:
                    time.sleep(1.5)
                    continue
                print("[rewardvideo-gate] 前置页连续点击 CTA 未推进，执行收尾恢复")
                return recover_to_welfare_page(d, max_rounds=8)
            else:
                rewardvideo_gate_hits = 0
                pre_gate_stall_hits = 0
                pre_gate_close_fail_hits = 0

        if is_pre_countdown_gate(full_text):
            if landing_rounds >= 1:
                jump_confirmed = True
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
                    print("[gate-post] 页面无进展，尝试受控退出 Rewardvideo")
                    if try_exit_rewardvideo_page(d, items=items, source="gate-post"):
                        gate_post_stall_hits = 0
                        continue
                    gate_post_stall_hits += 1
                    if gate_post_stall_hits >= 6:
                        print("[gate-post] 连续无进展，触发收尾回退")
                        return recover_to_welfare_page(d, max_rounds=12)
                continue
            advanced = advance_pre_countdown_gate(d, items)
            if advanced:
                pre_gate_stall_hits = 0
                if sig_stable_hits >= 4:
                    print("[gate] 连续点击后页面仍未变化，改用 back+滑动切换层级")
                    d.press("back")
                    time.sleep(0.9)
                    d.swipe_ext("up", scale=0.22)
                    time.sleep(0.8)
                time.sleep(1.0)
                continue
            if sig_stable_hits >= 3:
                if "RewardvideoPortraitADActivity" in activity:
                    if try_close_rewardvideo_recommend_popup(d, items=items, source="gate-stall"):
                        pre_gate_stall_hits = 0
                        time.sleep(1.0)
                        continue
                    pre_gate_stall_hits += 1
                    if pre_gate_stall_hits >= 4:
                        print("[gate] Rewardvideo 前置页长时间无变化，直接收尾恢复")
                        return recover_to_welfare_page(d, max_rounds=8)
                    print("[gate] Rewardvideo 前置页长时间无变化，跳过底部兜底点击，避免误跳外部应用")
                    time.sleep(1.2)
                else:
                    print("[gate] 页面长时间无变化，执行底部中点兜底点击")
                    w, h = d.window_size()
                    d.click(int(w * 0.5), int(h * 0.86))
                    time.sleep(1.2)
            continue

        cta_prompt_words = ["了解详情", "了解更多", "继续看", "继续观看", "去看看"]
        is_ad_context = (
            "RewardvideoPortraitADActivity" in activity
            or "ADActivity" in activity
            or any(k in full_text for k in AD_LAYER_HINT_WORDS)
        )
        if is_ad_context and any(k in full_text for k in cta_prompt_words):
            if landing_rounds >= 1:
                jump_confirmed = True
                sec3 = detect_countdown_seconds(full_text)
                if sec3 is not None and sec3 > 0:
                    wait3 = min(max(sec3 // 2 + 1, 2), 8)
                    print(f"[cta-post] 落地页已完成，等待计时 {sec3}s -> sleep {wait3}s")
                    time.sleep(wait3)
                else:
                    time.sleep(1.2)
                continue
            if click_text_candidate(d, items, cta_prompt_words, region="all"):
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

        if "RewardvideoPortraitADActivity" in activity and rewardvideo_gate_hits > 0:
            print("[rewardvideo-gate] 仍在前置页，暂不执行 back")
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


def bootstrap_to_welfare_center(d, max_rounds=8):
    print("初始化：强制启动起点并进入福利中心")
    start_app(d, QD_APP, init=True)
    time.sleep(3.0)

    for i in range(max_rounds):
        force_back_to_maingroup(d, max_steps=5)
        items = page_items(d, prefer_hierarchy=True)
        _, activity = get_current_app(d)
        activity = activity or ""
        if is_welfare_task_page(d, items, activity):
            print("初始化完成：已在福利任务页")
            return True

        if "MainGroupActivity" in activity:
            if enter_welfare_center_selector_first(d, max_rounds=4):
                continue

        # 其他页面用回退恢复
        print(f"初始化第 {i + 1}/{max_rounds} 轮：尝试回退恢复到福利页")
        if recover_to_welfare_page(d, max_rounds=6):
            return True
        start_app(d, QD_APP, init=False)
        time.sleep(2.0)

    return False


def run_qidian_fuli_tasks(d):
    print("开始执行 qidian 福利中心广告任务（仅“完成任务得奖励”卡片）")

    # 预处理：如果当前残留在广告页/外部页，先回到福利中心
    items0 = page_items(d, prefer_hierarchy=True)
    _, activity0 = get_current_app(d)
    if not is_welfare_task_page(d, items0, activity0):
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

    def ensure_welfare_ready(stage):
        items_now = page_items(d, prefer_hierarchy=True)
        _, act_now = get_current_app(d)
        if is_welfare_task_page(d, items_now, act_now):
            return True
        print(f"[ensure] {stage}: 当前不在福利页，先回退恢复")
        if recover_to_welfare_page(d, max_rounds=10):
            return True
        print(f"[ensure] {stage}: 回退失败，执行初始化重进福利中心")
        return bootstrap_to_welfare_center(d, max_rounds=4)

    for spec in TASK_SPECS:
        if not ensure_welfare_ready(f"任务开始-{spec['name']}"):
            task_report.append(
                {
                    "task": spec["name"],
                    "status": "executed_failed",
                    "note": "无法恢复到福利任务页，任务终止",
                }
            )
            stats["executed_failed"] += 1
            break
        print(f"准备处理任务: {spec['name']}")
        handled = False
        task_status = "not_found"
        task_note = "未定位到任务行"
        max_clicks = int(spec.get("max_clicks", 1))
        executed_times = 0
        stop_by_non_pending = False

        for run_idx in range(max_clicks):
            if not ensure_welfare_ready(f"{spec['name']}-第{run_idx + 1}轮"):
                handled = True
                task_status = "executed_failed"
                task_note = f"{spec['name']} 第{run_idx + 1}轮前无法恢复到福利页"
                stats["executed_failed"] += 1
                break
            print(f"{spec['name']} 第 {run_idx + 1}/{max_clicks} 轮检查")
            round_finished = False
            for attempt in range(6):
                rows = welfare_task_rows(d)
                row = next((r for r in rows if any(k in r["full_text"] for k in spec["keywords"])), None)
                action = row["action"] if row else None
                if row is None:
                    items = page_items(d, prefer_hierarchy=True)
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
                row_text = row.get("raw_text") or row.get("full_text") or row.get("text") or ""
                print(f"任务行命中: {row_text} | 动作: {action_text}")

                is_pending = any(k in action_text for k in PENDING_ACTION_TEXTS)

                # 多轮任务：只要按钮不再是“去完成/去领取”，即视作该任务已完成
                if max_clicks > 1 and not is_pending:
                    handled = True
                    stop_by_non_pending = True
                    task_status = "executed_success" if executed_times > 0 else "already_done"
                    task_note = f"执行{executed_times}次后按钮变为: {action['raw_text']}"
                    if executed_times > 0:
                        stats["executed_success"] += 1
                    else:
                        stats["already_done"] += 1
                    round_finished = True
                    break

                if any(k in action_text for k in DONE_ACTION_TEXTS):
                    print("该任务已完成或暂不可执行，跳过")
                    handled = True
                    task_status = "already_done"
                    task_note = f"按钮状态: {action['raw_text']}"
                    stats["already_done"] += 1
                    round_finished = True
                    break

                if action_text.startswith("剩"):
                    print("该任务处于冷却倒计时，暂不可执行，跳过")
                    handled = True
                    task_status = "already_done"
                    task_note = f"冷却中: {action['raw_text']}"
                    stats["already_done"] += 1
                    round_finished = True
                    break

                if is_pending:
                    click_center(d, action)
                    time.sleep(2.0)
                    flow_ok = execute_after_click_task(d, timeout=210)
                    back_ok = recover_to_welfare_page(d, max_rounds=10)
                    if not back_ok:
                        back_ok = ensure_welfare_ready(f"{spec['name']}-第{executed_times + 1}次执行后")
                    handled = True
                    executed_times += 1
                    if flow_ok or back_ok:
                        task_status = "executed_success"
                        task_note = f"已执行{executed_times}次，当前按钮: {action['raw_text']}"
                        round_finished = True
                        break
                    task_status = "executed_failed"
                    task_note = f"第{executed_times}次执行后回退异常: {action['raw_text']}"
                    stats["executed_failed"] += 1
                    round_finished = True
                    break

                # 未知动作（既不是已完成也不是去完成），不执行点击，避免误触
                task_status = "unknown_action"
                task_note = f"检测到未知按钮文案，已跳过: {action['raw_text']}"
                d.swipe_ext("up", scale=0.18)
                time.sleep(1.0)

            # 单轮任务执行一次就结束；多轮任务执行成功后继续下一轮，直到按钮非 pending
            if not round_finished:
                break
            if task_status == "executed_failed":
                break
            if task_status == "already_done":
                break
            if max_clicks == 1:
                if task_status == "executed_success":
                    stats["executed_success"] += 1
                break
            if stop_by_non_pending:
                break

        if not handled:
            print(f"未成功执行任务: {spec['name']}（可能不在当前批次或已隐藏）")
            if task_status == "not_found":
                stats["not_found"] += 1
            elif task_status == "unknown_action":
                stats["not_found"] += 1
        elif max_clicks > 1 and task_status == "executed_success" and not stop_by_non_pending:
            # 多轮任务达到 max_clicks 上限，视作一次成功
            stats["executed_success"] += 1
            task_note = f"已执行至上限{max_clicks}次，最终按钮仍可执行"

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
    if not bootstrap_to_welfare_center(d, max_rounds=8):
        raise RuntimeError("初始化失败：未能自动进入起点福利中心")
    run_qidian_fuli_tasks(d)


if __name__ == "__main__":
    main()
