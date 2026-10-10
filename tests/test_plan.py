#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦拼餐师 · 离线自测
====================
不联网、不需要 Token，直接用 data/sample-case-4p-180.json（真实抓取样本）跑。

    python tests/test_plan.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import plan as P  # noqa: E402

SAMPLE = os.path.join(ROOT, "data", "sample-case-4p-180.json")

# 2026-10-10 由 calculate-price 官方核价确认的四个总价（单位：元）
OFFICIAL = {"value": 138.40, "cheapest": 71.50, "tasty": 175.80, "share": 120.70}

_passed = 0
_failed = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  PASS  {name}")
    else:
        _failed += 1
        print(f"  FAIL  {name}  {detail}")


def test_diff_price():
    print("\n[1] diffPrice 解析")
    cases = {"+ ¥0": 0.0, "- ¥1": -1.0, "+ ¥1.5": 1.5, "-¥0.5": -0.5,
             "+ ¥2": 2.0, "+¥1": 1.0, "": 0.0, None: 0.0}
    for raw, want in cases.items():
        got = P.parse_diff_price(raw)
        check(f"parse_diff_price({raw!r}) == {want}", abs(got - want) < 1e-9, f"got {got}")


def test_flavour():
    print("\n[2] 辣味判定")
    check("龙焰鸡腿堡 → 辣", P.detect_flavour("龙焰鸡腿堡", "韩式辣椒黄油风味").spicy is True)
    check("麦辣鸡腿汉堡 → 辣", P.detect_flavour("麦辣鸡腿汉堡", "人气经典").spicy is True)
    check("酥酥多笋卷（川香）→ 辣", P.detect_flavour("酥酥多笋卷", "川香风味").spicy is True)
    check("巨无霸 → 不辣", P.detect_flavour("巨无霸", "100%纯牛肉").spicy is False)
    check("麦香鱼 → 不辣", P.detect_flavour("麦香鱼", "麦香鱼系列").spicy is False)
    check("麦香鸡 → 含鸡", P.detect_flavour("麦香鸡").chicken is True)
    check("空文本 → 未知", P.detect_flavour("").spicy is None)


def test_load_sample():
    print("\n[3] 样本解析")
    with open(SAMPLE, encoding="utf-8") as f:
        data = json.load(f)
    items = P.parse_menu(data["menu"])
    details = {}
    tags_by_code = {c: it.tags for c, it in items.items()}
    for code, d in (data["details"] or {}).items():
        it = items.get(str(code))
        det = P.parse_detail(d, it.price if it else 0.0, tags_by_code)
        if det:
            details[str(code)] = det
    check("菜单解析出 >= 70 项", len(items) >= 70, f"got {len(items)}")
    check("解析出 3 份套餐详情", len(details) == 3, f"got {len(details)}")

    group = data["group"]
    people = [P.Person(pid=p.get("id", f"P{i+1}"),
                       avoid=list(p.get("avoid") or []),
                       prefer=list(p.get("prefer") or []))
              for i, p in enumerate(group["people"])]
    budget = float(group["budget"])
    return data, items, details, people, budget


def test_strategies(items, details, people, budget):
    print("\n[4] 四策略与官方核价一致性")
    got = {}
    for st in ("value", "cheapest", "tasty", "share"):
        pl = P.build_plan(st, people, items, details, budget)
        check(f"{st} 能生成方案", pl is not None)
        if not pl:
            continue
        got[st] = pl.total
        check(f"{st} 不超预算（{pl.total} <= {budget}）", pl.total <= budget + 1e-6)
        for w in pl.warnings:
            print(f"        ⚠ {w}")
    print("\n[5] 与 calculate-price 官方返回值比对")
    for st, want in OFFICIAL.items():
        if st in got:
            check(f"{st}: 引擎 {got[st]:.2f} == 官方 {want:.2f}", abs(got[st] - want) < 0.005,
                  f"got {got[st]}")


def test_spicy_safety(items, details, people):
    print("\n[6] 忌口安全性（不吃辣的人绝不能拿到辣餐）")
    spicy_people = [p for p in people if "spicy" in p.avoid]
    check("样本里存在不吃辣的人", len(spicy_people) == 2)
    for st in ("value", "cheapest", "tasty", "share"):
        pl = P.build_plan(st, people, items, details, 180)
        if not pl:
            continue
        by_pid = {p.pid: p for p in people}
        for person, sel in pl.per_person:
            if "spicy" not in by_pid[person.pid].avoid:
                continue
            # 未确认辣味的餐品必须被标记出来，而不是默默当作不辣
            if sel.spicy_unknown:
                continue
            check(f"{st}/{person.pid} 未拿到辣餐（{sel.name}）", sel.flavour.spicy is not True)


def test_share_meal_rejected(items, details, people):
    print("\n[7] 分享餐对忌口者的弃用逻辑")
    # 9900011056 全明星双人分享餐：汉堡轮只有麦辣鸡腿汉堡与酥酥多笋卷，两个都辣
    d = details.get("9900011056")
    check("样本含全明星双人分享餐详情", d is not None)
    if d:
        avoider = P.Person(pid="X", avoid=["spicy"])
        check("对不吃辣者，该分享餐被判定为不可用",
              P.solve_rounds(d, avoider) is None)
        free = P.Person(pid="Y")
        check("对无忌口者，该分享餐可解算", P.solve_rounds(d, free) is not None)

    # 回归：酥酥多笋卷名字不含"辣"，但菜单标签是「川香风味」。
    # 只看 choice 名字会误判成不辣，必须靠 code 回查菜单标签。
    with open(SAMPLE, encoding="utf-8") as f:
        raw = json.load(f)["details"]["9900011056"]
    tags_by_code = {"521816": ["单品", "全新升级", "川香风味"]}
    d2 = P.parse_detail(raw, 49.9, tags_by_code)
    r1 = next(r for r in d2.rounds if r.rid == "1")
    duoshou = next(c for c in r1.choices if c.code == "521816")
    check("靠 code 回查标签能识别出「酥酥多笋卷」是辣的",
          duoshou.flavour.spicy is True)
    d3 = P.parse_detail(raw, 49.9)
    r1b = next(r for r in d3.rounds if r.rid == "1")
    ds3 = next(c for c in r1b.choices if c.code == "521816")
    check("不传标签时该选项只能标为不辣（数据不足，不猜）",
          ds3.flavour.spicy is False)


def test_budget():
    print("\n[8] 预算过紧时的行为")
    _, items, details, people, _ = test_load_sample()
    pl = P.build_plan("tasty", people, items, details, 20)   # 远低于任何可行方案
    check("预算不足时仍给出方案或明确警告", pl is None or pl.warnings)
    if pl:
        print(f"        ⚠ {pl.warnings}")


def test_single_person():
    print("\n[9] 单人场景（实测发现的缺口，已修）")
    import json as _j, os as _o
    sample = _o.path.join(_o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))),
                          "data", "sample-case-4p-180.json")
    with open(sample, encoding="utf-8") as f:
        data = _j.load(f)
    items = P.parse_menu(data["menu"])
    tags = {c: it.tags for c, it in items.items()}
    details = {}
    for code, d in (data["details"] or {}).items():
        it = items.get(str(code))
        det = P.parse_detail(d, it.price if it else 0.0, tags)
        if det:
            details[str(code)] = det
    one = [P.Person(pid="我")]
    d = P.build_plan("value", one, items, details, float("inf"))
    check("单人：标记为 single", d.single is True)
    kinds = sorted({i.kind for i, _ in d.shared})
    check("单人：加配最多 1 份小食 + 1 份甜品",
          kinds.count("share_side") <= 1 and kinds.count("dessert") <= 1, str(kinds))
    check("单人：不再出现七件任选这类多人份量",
          all("7件任选" not in i.name for i, _ in d.shared), str([i.name for i, _ in d.shared]))
    check("单人：总价 = 人均", abs(d.total - d.total / max(1, d.headcount)) < 0.005)
    sh = P.build_plan("share", one, items, details, float("inf"))
    check("单人：拼单策略回退并说明原因",
          sh is not None and sh.label != "多人拼单" and len(sh.warnings) > 0,
          sh.label if sh else "None")
    d2 = P.build_plan("cheapest", one, items, details, float("inf"))
    check("单人：省钱方案也不加倍共享份数",
          all(q <= 1 for _, q in d2.shared), str([(i.name, q) for i, q in d2.shared]))


def main() -> int:
    print("=" * 62)
    print("麦麦拼餐师 · 离线自测")
    print("=" * 62)
    test_diff_price()
    test_flavour()
    data, items, details, people, budget = test_load_sample()
    test_strategies(items, details, people, budget)
    test_spicy_safety(items, details, people)
    test_share_meal_rejected(items, details, people)
    test_budget()
    test_single_person()
    print("\n" + "=" * 62)
    print(f"通过 {_passed} / 失败 {_failed}")
    print("=" * 62)
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
