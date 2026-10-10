#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦拼餐师 · 零尾差 AA 分账
==========================
把一份拼餐方案分摊到每个人头上，**合计与实付金额分毫不差**。

为什么全程用整数分
----------------
浮点数在钱这件事上不可靠。0.1 + 0.2 != 0.3，13.9 / 3 = 4.6333...，
累计四舍五入后经常差几分钱。本模块把所有金额转成**整数分**再运算，
余数按固定顺序分配，保证 sum(每人) == 实付，一分不差。

分摊规则
--------
1. **个人专属餐**（每人各自那份套餐/单品）→ 归本人
2. **共享餐**（薯条、派、鸡翅等）→ 在参与者之间均分，余数按序分配
3. **分享餐分组**（一份双人餐覆盖 2 人）→ 只在该组成员之间分摊
4. **优惠金额** → 视为全桌共享，按人数均分，余数同样按序分配

「按序分配」的含义：若 10 元分给 3 人，得 334/333/333 分（先到先得），
而不是 333.33/333.33/333.33 再各自四舍五入——后者必然差钱。

用法:
    python split_bill.py plans.json [策略名] [--discount 13.5]
"""
from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional


def to_cents(yuan: Any) -> int:
    """元 → 分。字符串和浮点都能吃，四舍五入到分。"""
    return int(round(float(yuan) * 100))


def to_yuan(cents: int) -> float:
    return round(cents / 100, 2)


def allocate(total_cents: int, n: int) -> List[int]:
    """把 total_cents 拆成 n 份，余数按序分配，保证求和精确等于原值。"""
    if n <= 0:
        return []
    base = total_cents // n
    rem = total_cents - base * n
    return [base + (1 if i < rem else 0) for i in range(n)]


def split_plan(plan: Dict[str, Any], discount_cents: int = 0) -> Dict[str, Any]:
    """
    对一份方案做分账。
    discount_cents：整单优惠金额（元），按人数均摊。
    """
    people = [a["person"] for a in plan.get("assignments", [])]
    # 分享餐分组里的人也算参与者
    for g in plan.get("groups", []):
        for pid in g.get("members", []):
            if pid not in people:
                people.append(pid)
    n = len(people)
    if n == 0:
        return {"error": "方案里没有任何参与者"}

    idx = {pid: i for i, pid in enumerate(people)}
    # 每个人应承担的明细（单位：分）
    detail: Dict[str, List[Dict[str, Any]]] = {pid: [] for pid in people}

    # 1) 个人专属餐
    personal_total = 0
    for a in plan.get("assignments", []):
        pid = a["person"]
        c = to_cents(a["price"])
        personal_total += c
        detail[pid].append({"type": "personal", "name": a["itemName"], "cents": c})

    # 2) 分享餐分组：按成员均分该组份额
    group_total = 0
    for g in plan.get("groups", []):
        members = [p for p in g.get("members", []) if p in idx]
        if not members:
            continue
        subtotal = to_cents(g["subtotal"])
        group_total += subtotal
        parts = allocate(subtotal, len(members))
        for pid, part in zip(members, parts):
            detail[pid].append({
                "type": "group", "name": f"{g['itemName']}（{len(members)} 人共食）", "cents": part,
            })

    # 3) 共享餐：全桌均分
    shared_total = 0
    for s in plan.get("shared", []):
        subtotal = to_cents(s["subtotal"])
        shared_total += subtotal
        parts = allocate(subtotal, n)
        for pid, part in zip(people, parts):
            detail[pid].append({
                "type": "shared", "name": f"{s['name']} ×{s['qty']}（共享）", "cents": part,
            })

    # 4) 优惠：全桌共享，按人数均摊（负数）
    if discount_cents:
        parts = allocate(discount_cents, n)
        for pid, part in zip(people, parts):
            detail[pid].append({"type": "discount", "name": "整单优惠均摊", "cents": -part})

    # 汇总
    rows: List[Dict[str, Any]] = []
    for pid in people:
        subtotal = sum(x["cents"] for x in detail[pid])
        rows.append({
            "person": pid,
            "cents": subtotal,
            "yuan": to_yuan(subtotal),
            "items": detail[pid],
        })

    grand = sum(r["cents"] for r in rows)
    expected = personal_total + group_total + shared_total - discount_cents

    return {
        "strategy": plan.get("strategy"),
        "label": plan.get("label"),
        "headcount": n,
        "rows": rows,
        "totalCents": grand,
        "totalYuan": to_yuan(grand),
        "expectedCents": expected,
        "perCapitaCents": grand // n,
        "perCapitaYuan": to_yuan(grand // n),
        # 一分不差的校验：这是本模块存在的意义
        "balanced": grand == expected,
        "remainder": grand - expected,
    }


def render(result: Dict[str, Any]) -> str:
    if result.get("error"):
        return f"无法分账：{result['error']}"
    lines = [
        "=" * 60,
        f"【{result['label']}】分账 · {result['headcount']} 人",
        "=" * 60,
    ]
    for r in result["rows"]:
        lines.append(f"{r['person']}  应付 ¥{r['yuan']:.2f}")
        for it in r["items"]:
            sign = "-" if it["cents"] < 0 else ""
            lines.append(f"    {sign}¥{abs(it['cents'])/100:.2f}  {it['name']}")
    lines.append("-" * 60)
    lines.append(f"合计   ¥{result['totalYuan']:.2f}")
    lines.append(f"人均   ¥{result['perCapitaYuan']:.2f}")
    ok = result["balanced"]
    lines.append(f"校验   {'✅ 零尾差，合计与实付分毫不差' if ok else '❌ 差额 ' + str(result['remainder']) + ' 分'}")
    lines.append("=" * 60)
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("用法: python split_bill.py <plans.json> [策略名] [--discount 元]", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as f:
        plans = json.load(f)
    strategy = None
    discount = 0.0
    i = 2
    while i < len(argv):
        if argv[i] == "--discount" and i + 1 < len(argv):
            discount = float(argv[i + 1])
            i += 2
        else:
            strategy = argv[i]
            i += 1

    results = []
    for p in plans.get("plans", []):
        if strategy and p.get("strategy") != strategy:
            continue
        r = split_plan(p, to_cents(discount))
        r["officialTotalYuan"] = p.get("estimatedTotal")
        results.append(r)
    if not results:
        print("没有匹配的方案", file=sys.stderr)
        return 1
    for r in results:
        print(render(r))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
