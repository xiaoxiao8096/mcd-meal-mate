#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""零尾差分账自测。核心断言只有一条：分账合计必须精确等于实付。"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import split_bill as SB  # noqa: E402

_p = _f = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS  {name}")
    else:
        _f += 1
        print(f"  FAIL  {name}  {detail}")


def test_allocate():
    print("\n[1] 余数按序分配")
    check("10 元分 3 人 = 334/333/333", SB.allocate(1000, 3) == [334, 333, 333])
    check("求和精确等于原值", sum(SB.allocate(1000, 3)) == 1000)
    check("1 分钱分 3 人 = 1/0/0", SB.allocate(1, 3) == [1, 0, 0])
    check("负数（优惠）也能整除", sum(SB.allocate(-1000, 3)) == -1000)
    check("0 元分 4 人全为 0", SB.allocate(0, 4) == [0, 0, 0, 0])
    for total in range(0, 200):
        for n in range(1, 8):
            if sum(SB.allocate(total, n)) != total:
                check(f"allocate({total},{n}) 求和失配", False)
                return
    check("0~199 分 × 1~7 人 全部求和精确", True)


def test_cents():
    print("\n[2] 元/分换算")
    check("13.9 元 → 1390 分", SB.to_cents(13.9) == 1390)
    check("'8.5' 字符串 → 850 分", SB.to_cents("8.5") == 850)
    check("1390 分 → 13.9 元", SB.to_yuan(1390) == 13.9)
    check("0.1+0.2 浮点陷阱不影响本模块", SB.to_cents(0.1) + SB.to_cents(0.2) == SB.to_cents(0.3))


def test_split_real_plan():
    print("\n[3] 真实方案分账（4 人 180 元场景）")
    import plan as P
    sample = os.path.join(ROOT, "data", "sample-case-4p-180.json")
    with open(sample, encoding="utf-8") as f:
        data = json.load(f)
    items = P.parse_menu(data["menu"])
    tags = {c: it.tags for c, it in items.items()}
    details = {}
    for code, d in (data["details"] or {}).items():
        it = items.get(str(code))
        det = P.parse_detail(d, it.price if it else 0.0, tags)
        if det:
            details[str(code)] = det
    group = data["group"]
    people = [P.Person(pid=x.get("id", f"P{i+1}"),
                      avoid=list(x.get("avoid") or []),
                      prefer=list(x.get("prefer") or []))
              for i, x in enumerate(group["people"])]
    budget = float(group["budget"])

    for st in ("value", "cheapest", "tasty", "share"):
        pl = P.build_plan(st, people, items, details, budget)
        d = pl.to_dict(data["store"])
        r = SB.split_plan(d)
        check(f"{st}: 零尾差", r["balanced"], f"差额 {r['remainder']} 分")
        check(f"{st}: 合计等于引擎总价",
              abs(r["totalYuan"] - d["estimatedTotal"]) < 0.005,
              f"{r['totalYuan']} vs {d['estimatedTotal']}")
        # 与官方核价值（2026-10-10 实测）一致
        official = {"value": 138.40, "cheapest": 71.50, "tasty": 175.80, "share": 120.70}[st]
        check(f"{st}: 合计等于官方 calculate-price 值",
              abs(r["totalYuan"] - official) < 0.005, f"{r['totalYuan']} vs {official}")


def test_discount():
    print("\n[4] 带优惠的分账")
    import plan as P
    sample = os.path.join(ROOT, "data", "sample-case-4p-180.json")
    with open(sample, encoding="utf-8") as f:
        data = json.load(f)
    items = P.parse_menu(data["menu"])
    tags = {c: it.tags for c, it in items.items()}
    details = {}
    for code, dd in (data["details"] or {}).items():
        it = items.get(str(code))
        det = P.parse_detail(dd, it.price if it else 0.0, tags)
        if det:
            details[str(code)] = det
    people = [P.Person(pid=x["id"], avoid=list(x.get("avoid") or []),
                      prefer=list(x.get("prefer") or [])) for x in data["group"]["people"]]
    pl = P.build_plan("cheapest", people, items, details, 180.0)
    d = pl.to_dict(data["store"])

    for disc in (13.5, 15.9, 0.01, 7.77):
        r = SB.split_plan(d, SB.to_cents(disc))
        check(f"优惠 {disc} 元：仍然零尾差", r["balanced"], f"差额 {r['remainder']} 分")
        check(f"优惠 {disc} 元：合计 = 原价 - 优惠",
              abs(r["totalYuan"] - (d["estimatedTotal"] - disc)) < 0.005,
              f"{r['totalYuan']}")


def test_edge_cases():
    print("\n[5] 边界情况")
    r = SB.split_plan({"assignments": [], "groups": [], "shared": []})
    check("空方案返回错误而非崩溃", "error" in r)
    r = SB.split_plan({"assignments": [{"person": "A", "itemName": "x", "price": 10}], "shared": []})
    check("单人方案平衡", r["balanced"] and r["totalYuan"] == 10.0)
    plan2 = {
        "assignments": [{"person": "A", "itemName": "x", "price": 13.9},
                        {"person": "B", "itemName": "y", "price": 13.9}],
        "groups": [], "shared": [{"name": "薯条", "qty": 1, "subtotal": 16.0}],
    }
    r = SB.split_plan(plan2)
    check("两人 + 共享 16 元薯条：零尾差", r["balanced"], f"差额 {r['remainder']}")
    rows = {x["person"]: x["cents"] for x in r["rows"]}
    check("A = 13.9 + 8.0 = 21.9", rows["A"] == 2190, str(rows["A"]))
    check("B 同为 21.9", rows["B"] == 2190, str(rows["B"]))


def main() -> int:
    print("=" * 62)
    print("零尾差分账 · 离线自测")
    print("=" * 62)
    test_allocate()
    test_cents()
    test_split_real_plan()
    test_discount()
    test_edge_cases()
    print("\n" + "=" * 62)
    print(f"通过 {_p} / 失败 {_f}")
    print("=" * 62)
    return 0 if _f == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
