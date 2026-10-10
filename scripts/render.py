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
    "light":    "热量升序，配热量目标用",
    "value":    "花小钱吃好，套餐优先、差价最优",
    "cheapest": "能省则省，人均地板价",
    "tasty":    "当季新品优先，把预算花到位",
    "share":    "双人餐按份算，几个人几份就够",
}
ICON = {"light": "🥗", "value": "💰", "cheapest": "🥇", "tasty": "✨", "share": "👥"}


def _money(v: float) -> str:
    return f"¥{v:.2f}"


def _width(s: str) -> int:
    """按东亚全角算 2 列宽，用于对齐。"""
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in s)


def _row(left: str, right: str, tail: str = "") -> str:
    pad = max(1, W - 2 - _width(left) - _width(right))
    return f"{left}{' ' * pad}{right}{tail}"


def _kcal_str(v, meta: Dict[str, Any] = None) -> str:
    """
    逐项热量。查不到就明说未知，不留空也不猜。
    估算值加 `≈` 前缀——估算绝不能看起来像精确值。
    """
    if v is None:
        return "未知"
    mark = "≈" if (meta or {}).get("estimated") else ""
    return f"{mark}{v:.0f}kcal"


def _kcal_note(meta: Dict[str, Any]) -> str:
    """估算值要附来源说明，让人知道这个数怎么来的。"""
    if not meta or not meta.get("estimated"):
        return ""
    src = {"估算": "估算", "组件累加": "组件累加"}.get(meta.get("source", ""), meta.get("source", ""))
    note = meta.get("note") or ""
    return f"（{src}{'：' + note if note else ''}）"


def _assign_rows(plan: Dict[str, Any]):
    """返回 (主行, 轮次行或空串, 价格, 角标, 热量, 组件明细, 热量元信息)。"""
    out = []
    for a in plan.get("assignments", []):
        marks = []
        if a.get("spicyUnknown"):
            marks.append("辣度未确认")
        if a.get("isCampaignItem"):
            marks.append("当期活动")
        tail = ("  " + "·".join(marks)) if marks else ""
        rounds = " + ".join(r["name"] for r in a.get("rounds", []))
        sub = f"        └ {rounds}" if rounds else ""
        out.append((f"  {a['person']}  {a['itemName']}", sub, a["price"], tail,
                    a.get("kcal"), a.get("kcalComponents") or [],
                    a.get("kcalMeta") or {}))
    return out


def render_text(d: Dict[str, Any]) -> str:
    st = d.get("store", {})
    L: List[str] = [RULE, f"📍 {st.get('storeName', '?')}", RULE, ""]

    for p in d.get("plans", []):
        ico = ICON.get(p["strategy"], "🍟")
        L.append(f"{ico} {p['label']}  ·  {PITCH.get(p['strategy'], '')}")
        L.append("")
        L.append(f"   合计 {_money(p['estimatedTotal'])}      人均 {_money(p['perCapita'])}")
        # 热量合计行**始终显示**。算不出来就写"未知"，不能因为没有数字就不显示——
        # 那样看起来像"漏标"，而不是"数据缺失"。
        n = len(p.get("assignments", [])) or 1
        known = p.get("knownKcalItems", 0)
        est = p.get("estimatedKcalItems", 0) or 0
        exact = p.get("exactKcalItems", 0) or 0
        total = p.get("totalKcalItems") or (len(p.get("assignments", []))
                                           + len(p.get("shared", [])))
        if known == 0:
            L.append(f"   热量合计 未知    （0/{total} 项在营养表内，查不到）")
        else:
            line = (f"   热量合计 {p.get('totalKcal') or 0:.0f} kcal    "
                    f"人均 {(p.get('totalKcal') or 0)/n:.0f} kcal")
            if known < total:
                line += f"    （精确 {exact} 项" + (f"，估算 ≈{est} 项" if est else "") + f"，缺 {total - known} 项）"
            L.append(line)
        L.append("")

        rows = _assign_rows(p)
        if rows:
            for left, sub, price, tail, kcal, comps, meta in rows:
                L.append(_row(left, _money(price), tail))
                # 热量紧跟价格行，轮次明细再往后——保证"每个餐品下方就有热量"
                if comps:
                    detail = "  +  ".join(
                        f"{c['name']} {_kcal_str(c['kcal'])}" for c in comps)
                    L.append(f"        热量 {_kcal_str(kcal, meta)}{_kcal_note(meta)}   {detail}")
                else:
                    L.append(f"        热量 {_kcal_str(kcal, meta)}{_kcal_note(meta)}")
                if sub:
                    L.append(sub)
            L.append("   " + "·" * (W - 6))

        for g in p.get("groups", []):
            L.append(_row(f"  共食  {g['itemName']} ×{g['qty']}", _money(g["subtotal"])))
            L.append(f"        {'/'.join(g['members'])} 一起分")
        for sv in p.get("shared", []):
            word = "加配" if p.get("single") else "共享"
            qty = f" ×{sv['qty']}" if sv["qty"] > 1 else ""
            L.append(_row(f"  {word}  {sv['name']}{qty}", _money(sv["subtotal"])))
            L.append(f"        热量 {_kcal_str(sv.get('kcalTotal'), sv.get('kcalMeta') or {})}"
                     f"{_kcal_note(sv.get('kcalMeta') or {})}")

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
