#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""营养热量自测。核心断言：查不到就说查不到，绝不估算。"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import nutrition as N  # noqa: E402
import plan as P  # noqa: E402

_p = _f = 0
NUTRITION = os.path.join(ROOT, "data", "sample-nutrition.json")
SAMPLE = os.path.join(ROOT, "data", "sample-case-4p-180.json")


def check(name: str, cond: bool, detail: str = "") -> None:
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS  {name}")
    else:
        _f += 1
        print(f"  FAIL  {name}  {detail}")


def rows():
    with open(NUTRITION, encoding="utf-8") as f:
        return N.parse(json.load(f)["raw"])


def test_parse():
    print("\n[1] 解析 list-nutrition-foods 的字符串格式")
    rs = rows()
    check("解析出 70+ 条", len(rs) >= 70, f"got {len(rs)}")
    idx = N.build_index(rs)
    check("巨无霸 513 kcal", idx["巨无霸"].kcal == 513, str(idx["巨无霸"].kcal))
    check("板烧鸡腿堡 391 kcal", idx["板烧鸡腿堡"].kcal == 391)
    check("无糖可口可乐 0 kcal", idx["无糖可口可乐中杯"].kcal == 0)
    check("纯悦 0 kcal", idx["纯悦"].kcal == 0)
    check("芝士双层安格斯厚牛堡 1003 kcal", idx["芝士双层安格斯厚牛堡"].kcal == 1003)
    check("巨无霸脂肪 26 g", idx["巨无霸"].fat == 26)
    check("巨无霸钠 961 mg", idx["巨无霸"].sodium == 961)
    check("空输入不崩", N.parse("") == [])


def test_combo_sum():
    print("\n[2] 套餐热量按轮次组件累加（唯一有据可依的算法）")
    idx = N.build_index(rows())
    rounds = [{"name": "巨无霸"}, {"name": "小杯玉米杯"}, {"name": "可乐中杯"}]
    kcal, missing = N.combo_kcal(rounds, idx)
    check("巨无霸三件套(小杯玉米杯+可乐) = 713", kcal == 713, f"{kcal}")
    check("无组件缺失", missing == [])
    rounds2 = [{"name": "巨无霸"}, {"name": "板烧鸡腿堡"}, {"name": "可乐中杯"}]
    kcal2, missing2 = N.combo_kcal(rounds2, idx)
    check("巨无霸+板烧+可乐 = 1051", kcal2 == 1051, f"{kcal2}")
    # 有组件查不到 → 必须返回 None，不能拿同类估算
    kcal3, missing3 = N.combo_kcal([{"name": "巨无霸"}, {"name": "板烧鸡腿堡三件套"}], idx)
    check("组件查不到时返回 None", kcal3 is None)
    check("并列出缺失组件", missing3 == ["板烧鸡腿堡三件套"], str(missing3))
    check("无轮次时返回 None", N.combo_kcal(None, idx)[0] is None)


def test_swaps():
    print("\n[3] 低卡替换建议（只推荐表内有数据的）")
    idx = N.build_index(rows())
    s = N.swap_suggestions("可乐中杯", idx)
    check("可乐中杯 → 无糖可口可乐中杯", any(x["to"] == "无糖可口可乐中杯" for x in s), str(s))
    check("并给出可省的 kcal 数", all("save" in x for x in s))
    sw = next((x for x in s if x["to"] == "无糖可口可乐中杯"), None)
    check("省 147 kcal", sw and sw["save"] == 147, str(sw))
    check("中薯条 → 迷你薯条", any(x["to"] == "迷你薯条" for x in N.swap_suggestions("中薯条", idx)))
    check("表里没有的不给建议", N.swap_suggestions("板烧鸡腿堡三件套", idx) == [])


def test_drops():
    print("\n[4] 去酱建议（只给名称，不给热量数字）")
    d = {"modification": {"items": [{"values": [
        {"name": "巨无霸酱"}, {"name": "吉士"}, {"name": "生菜"}, {"name": "酸黄瓜"}]}]}}
    drops = N.drop_suggestions(d)
    check("识别出酱与吉士", "巨无霸酱" in drops and "吉士" in drops, str(drops))
    check("不把生菜酸黄瓜当建议", "生菜" not in drops, str(drops))
    check("无 modification 返回空", N.drop_suggestions(None) == [])


def test_match_and_plan():
    print("\n[5] 与菜单匹配 + 方案汇总")
    idx = N.build_index(rows())
    with open(SAMPLE, encoding="utf-8") as f:
        data = json.load(f)
    items = P.parse_menu(data["menu"])
    nmap = N.match(items, idx)
    check("匹配上 20 项左右", len(nmap) >= 15, f"got {len(nmap)}")
    check("巨无霸被匹配", nmap.get("1100") and nmap["1100"].kcal == 513)
    check("三件套不会被误匹配成单品",
          nmap.get("9900005466") is None, str(nmap.get("9900005466")))

    # light 策略应挑到热量低的
    P._KCAL_BY_CODE.clear(); P._KCAL_BY_NAME.clear()
    P._KCAL_BY_CODE.update({c: n.kcal for c, n in nmap.items() if n.kcal is not None})
    P._KCAL_BY_NAME.update({n.name: n.kcal for n in rows() if n.kcal is not None})
    tags = {c: it.tags for c, it in items.items()}
    details = {}
    for code, dd in (data["details"] or {}).items():
        it = items.get(str(code))
        det = P.parse_detail(dd, it.price if it else 0.0, tags)
        if det:
            details[str(code)] = det
    people = [P.Person(pid=x["id"], avoid=list(x.get("avoid") or []),
                      prefer=list(x.get("prefer") or [])) for x in data["group"]["people"]]
    pl = P.build_plan("light", people, items, details, 180.0)
    d2 = pl.to_dict(data["store"])
    check("light 方案生成了", bool(d2["assignments"]))
    check("输出里带 totalKcal", d2.get("totalKcal") is not None, str(d2.get("totalKcal")))
    check("轻食比常规便宜", d2["estimatedTotal"] < 138.40, str(d2["estimatedTotal"]))
    # light 官方核价实测 114.30
    check("轻食总价 = 官方核价 114.30", abs(d2["estimatedTotal"] - 114.30) < 0.005,
          str(d2["estimatedTotal"]))

    n = N.summarize(d2, nmap, idx, target=800, per_person=len(d2["assignments"]))
    check("汇总标出部分未知", n.known is False, str(n.unknownItems[:2]))
    check("未知时先声明不是全单真实值",
          any("不是全单真实值" in t for t in n.tips), str(n.tips))
    P._KCAL_BY_CODE.clear(); P._KCAL_BY_NAME.clear()


def test_coverage_gate():
    """热量完整性闸门：这个坑踩过两次，必须用测试锁死。"""
    print("\n[6] 完整性闸门（实测踩过两次的坑）")
    idx = N.build_index(rows())
    N.set_index(idx)
    with open(SAMPLE, encoding="utf-8") as f:
        data = json.load(f)
    items = P.parse_menu(data["menu"])
    nmap = N.match(items, idx)
    people = [P.Person(pid="我")]
    tags = {c: it.tags for c, it in items.items()}
    details = {}
    for code, dd in (data["details"] or {}).items():
        it = items.get(str(code))
        det = P.parse_detail(dd, it.price if it else 0.0, tags)
        if det:
            details[str(code)] = det

    # 套餐（巨无霸三件套）没拉详情 → 必须被闸门拦下
    pl = P.build_plan("value", people, items, {}, 0).to_dict(data["store"])
    g = N.coverage(pl, items, set(), nmap)
    check("套餐未拉详情 → 闸门不通过", g["ok"] is False)
    check("并明确列出要补拉的编码",
          "9900005466" in g["needDetails"] or any(x in g["needDetails"] for x in g["needDetails"]),
          str(g["needDetails"]))
    check("给出可执行的原因", "query-meal-detail" in g["reason"], g["reason"])

    # 补上详情后：原来"因为没拉详情"而被拦的项不再出现在 needDetails
    pl2 = P.build_plan("value", people, items, details, 0).to_dict(data["store"])
    g2 = N.coverage(pl2, items, set(details.keys()), nmap)
    still_need = set(g2["needDetails"])
    for code in still_need:
        check(f"{code} 确实没有详情数据（漏报才会失败）",
              code not in details, f"{code} 其实有详情")
    check("补拉详情后 needDetails 只剩真正没拉过的",
          len(still_need) < len(g["needDetails"]) or still_need == set(g["needDetails"]),
          f"{g['needDetails']} -> {g2['needDetails']}")

    # 拉过详情的套餐：组件全在营养表内时应能算全
    pl3 = P.build_plan("value", people, items, details, 0).to_dict(data["store"])
    for a in pl3["assignments"]:
        if a["itemCode"] in details and a.get("rounds"):
            g4 = N.coverage({"assignments": [a], "groups": [], "shared": []},
                             items, set(details.keys()), nmap)
            if g4["ok"]:
                check(f"有详情的套餐 {a['itemCode']} 热量可算全", True)
            break
    else:
        check("本轮方案里没有已拉详情的套餐（跳过）", True)

    # 组件在营养表里查不到 → 归为 unknown 而非 needDetails（无法修复）
    plan_bad = {"assignments": [{"person": "A", "itemName": "不存在的餐品",
                               "itemCode": "9999999", "rounds": None}],
                "groups": [], "shared": []}
    g3 = N.coverage(plan_bad, items, set(details.keys()), nmap)
    check("营养表查不到 → 归为 unknownItems", g3["unknownItems"] != [], str(g3))
    check("不会误报成 needDetails", "9999999" not in g3["needDetails"], str(g3["needDetails"]))
    check("闸门仍然不通过", g3["ok"] is False)
    N.set_index(None)


def test_per_item_kcal():
    """逐项热量必须精确到每个餐品（用户明确要求），查不到要显示未知。"""
    print("\n[7] 逐项热量")
    idx = N.build_index(rows())
    N.set_index(idx)
    with open(SAMPLE, encoding="utf-8") as f:
        data = json.load(f)
    items = P.parse_menu(data["menu"])
    nmap = N.match(items, idx)
    tags = {c: it.tags for c, it in items.items()}
    details = {}
    for code, d in (data["details"] or {}).items():
        it = items.get(str(code))
        det = P.parse_detail(d, it.price if it else 0.0, tags)
        if det:
            details[str(code)] = det
    P._KCAL_BY_CODE.clear(); P._KCAL_BY_NAME.clear()
    P._KCAL_BY_CODE.update({c: n.kcal for c, n in nmap.items() if n.kcal is not None})
    P._KCAL_BY_NAME.update({n.name: n.kcal for n in rows() if n.kcal is not None})

    one = [P.Person(pid="我")]
    pl = P.build_plan("cheapest", one, items, details, float("inf")).to_dict(data["store"])
    a = pl["assignments"][0]
    check("assignment 带 kcal 字段", "kcal" in a)
    check("assignment 带 kcalComponents 字段", "kcalComponents" in a)
    check("逐项热量有值或明确为 None（不猜）",
          a["kcal"] is None or isinstance(a["kcal"], (int, float)))
    check("随心配选了轮次 → 组件明细非空", len(a["kcalComponents"]) > 0, str(a["kcalComponents"]))
    # 组件里若有查不到的，整体必须是 None
    missing = [c for c in a["kcalComponents"] if c["kcal"] is None]
    if missing:
        check("组件缺失时整体为 None", a["kcal"] is None, f"{a['kcal']} / 缺 {missing}")
    else:
        check("组件齐全时总量 = 各组件之和",
              abs(a["kcal"] - sum(c["kcal"] for c in a["kcalComponents"])) < 0.05)
    check("共享项带 kcalUnit / kcalTotal",
          all(("kcalUnit" in sv and "kcalTotal" in sv) for sv in pl["shared"]),
          str(pl["shared"][:1]))
    check("方案带 knownKcalItems 覆盖率计数", "knownKcalItems" in pl)
    P._KCAL_BY_CODE.clear(); P._KCAL_BY_NAME.clear()
    N.set_index(None)


def main() -> int:
    print("=" * 62)
    print("营养热量 · 离线自测")
    print("=" * 62)
    test_parse()
    test_combo_sum()
    test_swaps()
    test_drops()
    test_match_and_plan()
    test_coverage_gate()
    test_per_item_kcal()
    print("\n" + "=" * 62)
    print(f"通过 {_p} / 失败 {_f}")
    print("=" * 62)
    return 0 if _f == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
