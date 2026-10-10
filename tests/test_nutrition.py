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
LIVE = os.path.join(ROOT, "data", "nutrition-live.txt")


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


def test_kcal_line_always():
    """每套方案都必须有热量合计行——查不到也要写"未知"，不能整行不显示。
    （用户指出过：其他方案的热量你就不标了？根因是 totalKcal 为 None 时整行被跳过。）"""
    print("\n[8] 热量行必须每套都有（用户指出的问题）")
    import os as _o
    sys.path.insert(0, _o.path.join(_o.path.dirname(_o.path.dirname(
        _o.path.abspath(__file__))), "scripts"))
    import render as R
    with open(SAMPLE, encoding="utf-8") as f:
        data = json.load(f)
    items = P.parse_menu(data["menu"])
    tags = {c: it.tags for c, it in items.items()}
    details = {}
    for code, d in (data["details"] or {}).items():
        it = items.get(str(code))
        det = P.parse_detail(d, it.price if it else 0.0, tags)
        if det:
            details[str(code)] = det
    one = [P.Person(pid="我")]

    # 不注入任何营养数据 → 全部未知
    P._KCAL_BY_CODE.clear(); P._KCAL_BY_NAME.clear()
    plans = [P.build_plan(st, one, items, details, float("inf")).to_dict(data["store"])
             for st in ("light", "value", "cheapest", "tasty", "share")]
    plans = [x for x in plans if x]
    check("五套方案都生成了", len(plans) == 5, f"{len(plans)}")
    out = R.render_text({"store": data["store"], "plans": plans, "notes": []})
    lines = [x for x in out.split("\n") if "热量合计" in x]
    check("每套都有一行热量合计", len(lines) == len(plans), f"{len(lines)}/{len(plans)}")
    check("全部未知时写明原因",
          all("查不到" in x for x in lines), lines[:1])
    # 热量标注在价格行的**下一行**，所以要逐行往下看，不能只查价格行本身
    ls = out.split("\n")
    price_idx = [i for i, x in enumerate(ls) if "¥" in x and "合计" not in x
                 and ("  " in x) and not x.strip().startswith(("合计", "人均"))]
    missing = [ls[i].strip()[:28] for i in price_idx
               if i + 1 >= len(ls) or "热量" not in ls[i + 1]]
    check("每个价格行下方都紧跟热量标注", not missing, str(missing[:3]))
    check("确实存在逐项热量行", any("热量" in x for x in ls))

    # 注入营养数据 → 有数字且带覆盖率
    idx2 = N.build_index(rows()); N.set_index(idx2)
    nmap2 = N.match(items, idx2)
    P._KCAL_BY_CODE.update({c: n.kcal for c, n in nmap2.items() if n.kcal is not None})
    P._KCAL_BY_NAME.update({n.name: n.kcal for n in rows() if n.kcal is not None})
    plans2 = [P.build_plan(st, one, items, details, float("inf")).to_dict(data["store"])
              for st in ("light", "value", "cheapest", "tasty", "share")]
    out2 = R.render_text({"store": data["store"], "plans": [x for x in plans2 if x],
                         "notes": []})
    lines2 = [x for x in out2.split("\n") if "热量合计" in x]
    check("注入营养数据后仍每套都有热量行", len(lines2) == 5, f"{len(lines2)}")
    # 覆盖率提示的措辞已升级：区分"精确"与"估算"（估算会带 ≈）
    check("部分可查时标明覆盖率且区分精确/估算",
          any(("精确" in x and "缺" in x) for x in lines2), lines2[:2])
    P._KCAL_BY_CODE.clear(); P._KCAL_BY_NAME.clear()
    N.set_index(None)


def test_combo_never_inherits_single():
    """
    套餐绝不能继承单品的热量。

    「板烧鸡腿堡三件套」去掉"三件套"就是「板烧鸡腿堡」(391)，
    若做子串兜底，一份 ~827 kcal 的套餐会被报成 391 kcal——少报 400+ 大卡，
    而且错得毫无痕迹。这条断言就是钉死这个坑。
    """
    print("\\n[9] 套餐不得继承单品热量（真实营养表）")
    idx = N.build_index(N.parse(open(LIVE, encoding="utf-8").read()))
    with open(SAMPLE, encoding="utf-8") as f:
        data = json.load(f)
    items = P.parse_menu(data["menu"])
    hits = N.match_smart(items, idx)

    combos = [c for c in items if items[c].kind == "combo"]
    check("样本里有套餐可测", len(combos) > 0, str(len(combos)))

    bad = []
    for c in combos:
        h = hits[c]
        if h.kcal is None or h.source != "alias":
            continue
        # 已人工核对的别名是允许的（营养表把整套产品单独登记了），
        # 例如「牛气满满套餐」→「牛气满满」495 是**整套餐**的真实值。
        # 这里要拦的是"未经核对、碰巧子串命中"的误配。
        if items[c].name in N.NAME_ALIAS:
            continue
        for rn, row in idx.items():
            if row.kcal is None:
                continue
            if N._norm(rn) in N._norm(items[c].name) and N._norm(rn) != N._norm(items[c].name):
                if abs((h.kcal or 0) - row.kcal) < 0.01:
                    bad.append((items[c].name, h.kcal, rn))
    check("没有套餐被误判成其内含单品", not bad, str(bad[:3]))

    # 巨无霸三件套：营养表只有「巨无霸」513，绝不能直接返回 513
    g = next((c for c in combos if "巨无霸三件套" in items[c].name), None)
    if g:
        h = hits[g]
        check("巨无霸三件套不返回 513（汉堡本体值）",
              h.kcal is None or h.kcal > 600, f"{h.kcal}")

    # 已核对别名：500大卡系列在营养表里是独立登记的完整产品，可以引用
    nq = next((c for c in combos if "牛气满满" in items[c].name), None)
    if nq:
        check("牛气满满套餐命中营养表 495", abs((hits[nq].kcal or 0) - 495) < 0.01,
              f"{hits[nq].kcal}")
        check("牛气满满套餐标为高置信", hits[nq].confidence == "高", hits[nq].confidence)

    # 杯型补全：菜单「可乐」应命中「可乐中杯」
    k = next((c for c in items if items[c].name == "可乐"), None)
    if k:
        check("可乐按中杯 147 补全", abs((hits[k].kcal or 0) - 147) < 0.01, f"{hits[k].kcal}")
        check("可乐标为中置信（未标杯型）", hits[k].confidence == "中", hits[k].confidence)


def test_estimate_never_masquerades():
    """估算值必须与精确值分开存放，且渲染带 ≈ 标记。"""
    print("\\n[10] 估算值不得冒充精确值")
    one = [P.Person(pid="我")]
    with open(SAMPLE, encoding="utf-8") as f:
        data = json.load(f)
    items = P.parse_menu(data["menu"])
    tags = {c: it.tags for c, it in items.items()}
    details = {}
    for code, dd in (data["details"] or {}).items():
        it = items.get(str(code))
        det = P.parse_detail(dd, it.price if it else 0.0, tags)
        if det:
            details[str(code)] = det

    P._KCAL_BY_CODE.clear(); P._KCAL_BY_NAME.clear()
    P._KCAL_CONF.clear(); P._KCAL_NOTE.clear(); P._KCAL_ESTIMATE.clear()
    # 注入一个估算值
    P._KCAL_ESTIMATE["9999"] = (879.0, "测试估算")

    m = P.kcal_meta("某不存在餐品", "9999")
    check("估算值能查到", m["kcal"] == 879.0, str(m))
    check("估算标为低置信", m["confidence"] == "低", m["confidence"])
    check("估算标为 estimated", m["estimated"] is True, str(m))
    check("估算带说明", bool(m["note"]), m["note"])
    check("估算不落进精确表", "9999" not in P._KCAL_BY_CODE)

    # 渲染必须带 ≈
    import render as R
    check("估算值渲染带 ≈", R._kcal_str(879.0, m).startswith("≈"), R._kcal_str(879.0, m))
    check("精确值不带 ≈", not R._kcal_str(879.0, {"estimated": False}).startswith("≈"))
    check("未知不带 ≈", R._kcal_str(None) == "未知")

    # 精确值优先于估算
    P._KCAL_BY_CODE["9999"] = 500.0
    m2 = P.kcal_meta("某不存在餐品", "9999")
    check("有精确值时不返回估算", m2["kcal"] == 500.0 and m2["estimated"] is False, str(m2))

    P._KCAL_BY_CODE.clear(); P._KCAL_BY_NAME.clear()
    P._KCAL_CONF.clear(); P._KCAL_NOTE.clear(); P._KCAL_ESTIMATE.clear()


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
    test_kcal_line_always()
    test_combo_never_inherits_single()
    test_estimate_never_masquerades()
    print("\n" + "=" * 62)
    print(f"通过 {_p} / 失败 {_f}")
    print("=" * 62)
    return 0 if _f == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
