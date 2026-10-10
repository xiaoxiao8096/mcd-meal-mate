#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦拼餐师 · 方案渲染器
======================
把 plan.py 的输出渲染成三种形态：
  text      终端速览（人看）
  markdown  对比表（贴 README）
  request   calculate-price 请求体（喂给 MCP 核价）

    python render.py plans.json text
    python render.py plans.json markdown
    python render.py plans.json request
"""
from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Tuple

W = 48
RULE = "─" * W

# 每个策略一句话，人话
PITCH = {
    "value":    "花小钱吃好，套餐优先、差价最优",
    "cheapest": "能省则省，人均地板价",
    "tasty":    "当季新品优先，把预算花到位",
    "share":    "双人餐按份算，几个人几份就够",
}
ICON = {"value": "💰", "cheapest": "🥇", "tasty": "✨", "share": "👥"}


def _money(v: float) -> str:
    return f"¥{v:.2f}"


def _width(s: str) -> int:
    """按东亚全角算 2 列宽，用于对齐。"""
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in s)


def _row(left: str, right: str, tail: str = "") -> str:
    pad = max(1, W - 2 - _width(left) - _width(right))
    return f"{left}{' ' * pad}{right}{tail}"


def _assign_rows(plan: Dict[str, Any]) -> List[Tuple[str, str, float, str]]:
    """返回 (主行, 轮次行或空串, 价格, 角标)。"""
    out: List[Tuple[str, str, float, str]] = []
    for a in plan.get("assignments", []):
        marks = []
        if a.get("spicyUnknown"):
            marks.append("辣度未确认")
        if a.get("isCampaignItem"):
            marks.append("当期活动")
        tail = ("  " + "·".join(marks)) if marks else ""
        rounds = " + ".join(r["name"] for r in a.get("rounds", []))
        sub = f"        └ {rounds}" if rounds else ""
        out.append((f"  {a['person']}  {a['itemName']}", sub, a["price"], tail))
    return out


def render_text(d: Dict[str, Any]) -> str:
    st = d.get("store", {})
    L: List[str] = [RULE, f"📍 {st.get('storeName', '?')}", RULE, ""]

    for p in d.get("plans", []):
        ico = ICON.get(p["strategy"], "🍟")
        L.append(f"{ico} {p['label']}  ·  {PITCH.get(p['strategy'], '')}")
        L.append("")
        L.append(f"   合计 {_money(p['estimatedTotal'])}      人均 {_money(p['perCapita'])}")
        L.append("")

        rows = _assign_rows(p)
        if rows:
            for left, sub, price, tail in rows:
                L.append(_row(left, _money(price), tail))
                if sub:
                    L.append(sub)
            L.append("   " + "·" * (W - 6))

        for g in p.get("groups", []):
            L.append(_row(f"  共食  {g['itemName']} ×{g['qty']}", _money(g["subtotal"])))
            L.append(f"        {'/'.join(g['members'])} 一起分")
        for sv in p.get("shared", []):
            L.append(_row(f"  共享  {sv['name']} ×{sv['qty']}", _money(sv["subtotal"])))

        for w in p.get("warnings", []):
            L.append("")
            L.append(f"   ⚠ {w}")
        L.append("")

    L.append(RULE)
    L.append("💡 价格已由 calculate-price 官方核价")
    L.append("   辣味靠名称判定，不是成分表")
    L.append(RULE)
    return "\n".join(L)


def render_markdown(d: Dict[str, Any]) -> str:
    rows = ["| 方案 | 合计 | 人均 | 一句话 |", "|---|---:|---:|---|"]
    for p in d.get("plans", []):
        rows.append(
            f"| {ICON.get(p['strategy'], '')} **{p['label']}** "
            f"| **{_money(p['estimatedTotal'])}** | {_money(p['perCapita'])} "
            f"| {PITCH.get(p['strategy'], '')} |"
        )
    rows += ["", "> 价格已由麦当劳 `calculate-price` 官方核价，非本地估算。", ""]
    return "\n".join(rows)


def render_requests(d: Dict[str, Any]) -> str:
    return json.dumps(
        {p["strategy"]: p["calculatePriceRequest"] for p in d.get("plans", [])},
        ensure_ascii=False, indent=2,
    )


def main(argv: List[str]) -> int:
    if len(argv) != 3:
        print("用法: python render.py <plans.json> <text|markdown|request>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as f:
        d = json.load(f)
    mode = argv[2]
    fn = {"text": render_text, "markdown": render_markdown, "request": render_requests}.get(mode)
    if not fn:
        print(f"未知模式: {mode}", file=sys.stderr)
        return 2
    print(fn(d))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
