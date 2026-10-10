#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把营养表 + 菜单接成 plan.py 需要的输入（data/kcalByCode 等）。

    python scripts/build_nutrition_input.py <menu.json> <nutrition.txt> <out.json>

为什么要单独一步
----------------
plan.py 只认 code/name 两张热量表，且**分不出精确值与估算值**。
本脚本负责：调nutrition.resolve_kcal 逐项解析，把结果分成四类写进 JSON：

    kcalByCode/kcalByName  精确或高置信命中（营养表里查得到）
    kcalConfidence          置信度（高/中）
    kcalNote                取值依据（如"按可乐中杯计"）
    kcalEstimate            低置信估算（渲染时显示 ≈，绝不混进上面两张表）

⚠️ 估算只在**没有轮次组件数据**且用户明确要求时才生成，
    且必须写清 note。绝不静默估算。
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nutrition as N
import plan as P

# 营养表索引（供估算层查锚点）。由 build() 填充。
_NUTRITION_IDX: Dict[str, N.Nutrition] = {}


# 估算锚点：只在"营养表里确实有同类可依据的条目"时才引用，且必须写进 note。
# 数值来源是营养表里**真实存在**的条目，不是拍脑袋。
# ⚠️ 这些只用于"营养表没有该单品"时的低置信占位，渲染会显示 ≈。
_SIDE_ANCHORS = [
    # (关键词, kcal, 来源名)——按顺序取第一个命中的
    (("薯条",), 289.0, "中薯条"),
    (("玉米杯",), 53.0, "小杯玉米杯"),
    (("鸡块",), 213.0, "麦乐鸡5块"),
    (("薯饼",), 146.0, "脆薯饼"),
    (("鸡翅", "V翅"), 192.0, "薄皮焦香V翅"),
]
_DRINK_ANCHOR = (147.0, "可乐中杯")
_SIDE_ANCHOR = (289.0, "中薯条")


def _name_tokens(name: str) -> List[str]:
    """从餐品名里切出可用于在营养表里找同类的"词"（去掉括号与修饰）。"""
    base = N._norm(name)
    parts = [base]
    # 品牌/风味词：命中任意一个即可视为同类
    for tok in ("麦旋酷", "美汁源", "阳光橙", "阳光柠檬", "柠柠", "怡泉",
                "红茶", "鲜萃咖啡", "咖啡", "苹果汁", "雪碧", "可乐", "纯悦"):
        if tok in base:
            parts.append(tok)
    return parts


def _estimate_for(item, hit: N.KcalHit) -> Tuple[Optional[float], str]:
    """
    尽力给一个**可解释**的估算值。返回 (kcal, note)；给不出就 (None, "")。

    为什么允许估算
    --------------
    用户明确要求"每一道菜都要有热量"。查不到就留空的体验很差，
    所以这里给**带说明的低置信估算**，渲染层用 ≈ 标记，绝不冒充精确值。

    两条硬规则
    ----------
    1. 估算值只能由**营养表里真实存在的条目**推导（薯条→中薯条 289、
       可乐→可乐中杯 147），不能凭空给数。
    2. note 必须写清每一部分怎么来的，用户能自己判断可不可信。

    套餐：主餐（若能认出来）+ 小食锚点 + 饮品锚点。
    单品：能认出小食/饮品家族就用锚点，否则不给（宁可空着）。
    """
    name, kind = item.name, item.kind

    side = None
    for kws, kcal, src in _SIDE_ANCHORS:
        if any(k in name for k in kws):
            side = (kcal, src)
            break

    if kind == "combo":
        # 主餐：从名称里认出一个"营养表里有的汉堡/鸡排"
        main_k, main_src = None, None
        for rn, row in _NUTRITION_IDX.items():
            if row.kcal is None:
                continue
            rnb = N._norm(rn)
            if len(rnb) >= 3 and rnb in N._norm(name):
                main_k, main_src = row.kcal, rn
                break
        # 认不出主餐就**不给数**。只报"饮品 147"当三件套热量是荒谬的，
        # 用户看到会以为这套只要 147 大卡，比一个汉堡还低——错得离谱且误导。
        if main_k is None:
            return None, ""
        parts, total = [f"主餐 {main_src} {main_k:.0f}"], main_k
        # "三件套/套餐"按定义含小食与饮品；认不出具体小食就按中薯条计
        if side is not None:
            total += side[0]
            parts.append(f"小食 {side[1]} {side[0]:.0f}")
        else:
            total += _SIDE_ANCHOR[0]
            parts.append(f"小食 {_SIDE_ANCHOR[1]} {_SIDE_ANCHOR[0]:.0f}")
        total += _DRINK_ANCHOR[0]
        parts.append(f"饮品 {_DRINK_ANCHOR[1]} {_DRINK_ANCHOR[0]:.0f}")
        return round(total, 1), "套餐按 " + " + ".join(parts) + " 估算"

    if side is not None:
        return side[0], f"按营养表「{side[1]}」估算"

    # 饮品：先找营养表里的**同词**条目（麦炫酷/美汁源/阳光橙…），
    # 只有连一个同词条目都没有时，才退回可乐锚点并说明是按可乐计。
    for rn, row in _NUTRITION_IDX.items():
        if row.kcal is None:
            continue
        for token in _name_tokens(name):
            if token and token in rn and len(rn) <= len(name) + 4:
                return row.kcal, f"按营养表「{rn}」估算"
    if any(k in name for k in ("可乐", "雪碧", "芬达")):
        return _DRINK_ANCHOR[0], f"菜单未标杯型，按「{_DRINK_ANCHOR[1]}」估算"
    return None, ""


def build(menu_json: str, nutrition_txt: str,
          out_json: str) -> Dict[str, Any]:
    with open(menu_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    with open(nutrition_txt, "r", encoding="utf-8") as f:
        raw = f.read()

    rows = N.parse(raw)
    idx = N.build_index(rows)
    _NUTRITION_IDX.clear()
    _NUTRITION_IDX.update(idx)
    items = P.parse_menu(data.get("menu") or data)
    hits = N.match_smart(items, idx)

    by_code: Dict[str, float] = {}
    by_name: Dict[str, float] = {}
    conf: Dict[str, str] = {}
    note: Dict[str, str] = {}
    est: Dict[str, Dict[str, Any]] = {}
    unknown: List[str] = []

    for code, it in items.items():
        h = hits[code]
        if h.kcal is not None and h.confidence in ("高", "中"):
            by_code[code] = h.kcal
            conf[code] = h.confidence
            if h.note:
                note[code] = h.note
            continue
        k, n = _estimate_for(it, h)
        if k is not None:
            est[code] = {"kcal": round(k, 1), "note": n or "估算"}
        else:
            unknown.append(it.name)

    out = {
        "nutritionCount": len(rows),
        "menuItemCount": len(items),
        "matchedCount": len(by_code),
        "estimateCount": len(est),
        "unknownCount": len(unknown),
        "unknownItems": unknown,
        "kcalByCode": by_code,
        "kcalConfidence": conf,
        "kcalNote": note,
        "kcalEstimate": est,
    }
    # 名称表供套餐组件累加使用（组件按名字查）
    out["kcalByName"] = {items[c].name: v for c, v in by_code.items() if items[c].name}
    # 别名也要进名称表：套餐轮次组件（如"可乐麦炫酷"）按名字查热量时用得上。
    # 同时补上按默认杯型解析的条目，让组件名（可乐/雪碧）也能查到。
    size_idx = N._build_size_index(idx)
    for alias, target in N.NAME_ALIAS.items():
        if target in idx and idx[target].kcal is not None:
            out["kcalByName"].setdefault(alias, idx[target].kcal)
            conf[alias] = "高"
            note[alias] = f"营养表独立登记为「{target}」"
    for base, cands in size_idx.items():
        pick = N._pick_by_size(cands)
        if pick and pick.kcal is not None and base not in out["kcalByName"]:
            out["kcalByName"][base] = pick.kcal
            conf.setdefault(base, "中")
            note.setdefault(base, f"菜单未标杯型，按「{pick.name}」计")

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return out


def main(argv: List[str]) -> int:
    if len(argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    r = build(argv[1], argv[2], argv[3])
    print(json.dumps({k: v for k, v in r.items()
                      if not isinstance(v, (dict, list))}, ensure_ascii=False, indent=2))
    print(f"\n精确/高置信命中 {r['matchedCount']}  估算 {r['estimateCount']}  "
          f"未知 {r['unknownCount']} / 共 {r['menuItemCount']}")
    if r["unknownCount"]:
        print("\n仍未知（不猜，需 query-meal-detail 或营养表补录）:")
        for n in r["unknownItems"]:
            print(f"  - {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))